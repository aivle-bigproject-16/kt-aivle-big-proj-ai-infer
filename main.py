import os
from time import perf_counter, sleep

from fastapi import FastAPI, HTTPException

from adapter_factory import build_adapter
from adapters import InferenceAdapter
from downloader import ImageDownloadError, download_image
from schemas import InferRequest, InferResponse
from settings import load_settings


LATENCY_MS = int(os.getenv("STUB_LATENCY_MS", "800"))
SETTINGS = load_settings()

app = FastAPI(title="ai-infer")

CT_ADAPTER = build_adapter("ct", SETTINGS)
RGB_ADAPTER = build_adapter("rgb", SETTINGS)


def _infer(
    req: InferRequest,
    adapter: InferenceAdapter,
) -> dict:
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

    prediction = adapter.predict(image_bytes)
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
    return _infer(req, CT_ADAPTER)


@app.post("/infer/rgb", response_model=InferResponse)
def infer_rgb(req: InferRequest) -> dict:
    return _infer(req, RGB_ADAPTER)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mode": SETTINGS.inference_mode,
        "models": {
            "ct": True,
            "rgb": True,
        },
    }
