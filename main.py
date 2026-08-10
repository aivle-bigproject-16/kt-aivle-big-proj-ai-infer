import logging
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from threading import BoundedSemaphore
from time import perf_counter, sleep

from fastapi import FastAPI, Header, HTTPException, status

from adapter_factory import build_adapter
from adapters import InferenceAdapter
from cell_analysis import process_cell_analysis
from downloader import ImageDownloadError, download_image
from schemas import (
    CellAnalysisAccepted,
    CellAnalysisRequest,
    InferRequest,
    InferResponse,
)
from settings import load_settings


logger = logging.getLogger(__name__)

LATENCY_MS = int(os.getenv("STUB_LATENCY_MS", "800"))
SETTINGS = load_settings()

app = FastAPI(title="ai-infer")


def _build(modality: str) -> tuple[InferenceAdapter | None, str | None]:
    """어댑터 생성 실패로 프로세스가 죽지 않게 한다.

    모델 파일이 없거나 세션 생성이 실패해도 서버는 뜨고, /health 가 사유를
    보고하며, 해당 모달 추론만 503 으로 거절한다.
    """
    try:
        return build_adapter(modality, SETTINGS), None
    except Exception as exc:
        logger.exception("failed to build the %s adapter", modality)
        return None, f"{type(exc).__name__}: {exc}"


CT_ADAPTER, CT_ADAPTER_ERROR = _build("ct")
RGB_ADAPTER, RGB_ADAPTER_ERROR = _build("rgb")
ANALYSIS_EXECUTOR = ThreadPoolExecutor(
    max_workers=int(os.getenv("CELL_ANALYSIS_WORKERS", "1")),
    thread_name_prefix="cell-analysis",
)
ANALYSIS_CAPACITY = BoundedSemaphore(SETTINGS.cell_analysis_queue_size)


def _analysis_finished(future) -> None:
    ANALYSIS_CAPACITY.release()
    error = future.exception()
    if error is not None:
        logger.error(
            "cell analysis background task failed",
            exc_info=(type(error), error, error.__traceback__),
        )


def _infer(
    req: InferRequest,
    adapter: InferenceAdapter | None,
    adapter_error: str | None,
) -> dict:
    if adapter is None:
        raise HTTPException(
            status_code=503,
            detail=f"inference adapter is unavailable: {adapter_error}",
        )

    started_at = perf_counter()

    try:
        image_bytes = download_image(req.image_url)
    except ImageDownloadError as exc:
        raise HTTPException(
            status_code=502,
            detail="failed to download inference image",
        ) from exc

    if SETTINGS.inference_mode == "stub":
        sleep(LATENCY_MS / 1000)

    try:
        prediction = adapter.predict(image_bytes)
    except ValueError as exc:
        # 전처리가 거부한 이미지다. 서버 잘못이 아니므로 4xx 로 답한다.
        raise HTTPException(
            status_code=422,
            detail="unprocessable inference image",
        ) from exc
    except Exception as exc:
        logger.exception(
            "inference failed for inspection %s", req.inspection_id
        )
        raise HTTPException(
            status_code=500,
            detail="inference failed",
        ) from exc

    latency_ms = max(
        0,
        round((perf_counter() - started_at) * 1000),
    )

    return {
        "inspection_id": req.inspection_id,
        **prediction,
        "latency_ms": latency_ms,
    }


@app.post("/infer/ct", response_model=InferResponse)
def infer_ct(req: InferRequest) -> dict:
    return _infer(req, CT_ADAPTER, CT_ADAPTER_ERROR)


@app.post("/infer/rgb", response_model=InferResponse)
def infer_rgb(req: InferRequest) -> dict:
    return _infer(req, RGB_ADAPTER, RGB_ADAPTER_ERROR)


@app.post(
    "/ai/cells/analyze",
    response_model=CellAnalysisAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_cell(
    req: CellAnalysisRequest,
    x_internal_api_key: str | None = Header(default=None),
) -> CellAnalysisAccepted:
    if (
        not SETTINGS.internal_api_key
        or not x_internal_api_key
        or not secrets.compare_digest(
            x_internal_api_key,
            SETTINGS.internal_api_key,
        )
    ):
        raise HTTPException(status_code=401, detail="unauthorized")

    if (
        not SETTINGS.backend_callback_url
        or req.callback_url != SETTINGS.backend_callback_url
    ):
        raise HTTPException(
            status_code=400,
            detail="callbackUrl does not match configured backend callback",
        )

    if not ANALYSIS_CAPACITY.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail="cell analysis queue is full",
        )

    adapters = {"CT": CT_ADAPTER, "RGB": RGB_ADAPTER}
    try:
        future = ANALYSIS_EXECUTOR.submit(
            partial(
                process_cell_analysis,
                req,
                adapters,
                SETTINGS.internal_api_key,
                SETTINGS.callback_timeout_seconds,
                SETTINGS.callback_max_attempts,
            )
        )
    except Exception:
        ANALYSIS_CAPACITY.release()
        raise
    future.add_done_callback(_analysis_finished)

    return CellAnalysisAccepted(
        accepted=True,
        request_id=req.request_id,
        inspection_id=req.inspection_id,
        battery_cell_id=req.battery_cell_id,
        status="ACCEPTED",
        accepted_at=datetime.now(timezone.utc),
    )


def _adapter_detail(
    adapter: InferenceAdapter | None,
    adapter_error: str | None,
) -> dict:
    if adapter is None:
        return {"adapter": None, "error": adapter_error}

    return {"adapter": type(adapter).__name__, "error": None}


@app.get("/health")
def health() -> dict:
    details = {
        "ct": _adapter_detail(CT_ADAPTER, CT_ADAPTER_ERROR),
        "rgb": _adapter_detail(RGB_ADAPTER, RGB_ADAPTER_ERROR),
    }
    models = {
        modality: detail["adapter"] is not None
        for modality, detail in details.items()
    }

    return {
        "status": "ok" if all(models.values()) else "degraded",
        "mode": SETTINGS.inference_mode,
        "models": models,
        "details": details,
    }
