import logging
import os
from time import perf_counter, sleep

from fastapi import FastAPI, HTTPException

from adapter_factory import build_adapter
from adapters import InferenceAdapter
from downloader import ImageDownloadError, download_image
from schemas import InferRequest, InferResponse
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
