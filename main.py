import os
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from adapters import InferenceAdapter, StubAdapter
from downloader import ImageDownloadError, download_image


LATENCY_MS = int(os.getenv("STUB_LATENCY_MS", "800"))

app = FastAPI(title="ai-infer")

CT_ADAPTER = StubAdapter("ct")
RGB_ADAPTER = StubAdapter("rgb")


class InferRequest(BaseModel):
    inspection_id: int
    image_key: str
    image_url: str


def _infer(
    req: InferRequest,
    adapter: InferenceAdapter,
) -> dict:
    try:
        image_bytes = download_image(req.image_url)
    except ImageDownloadError as exc:
        raise HTTPException(
            status_code=502,
            detail="failed to download inference image",
        ) from exc

    time.sleep(LATENCY_MS / 1000)

    prediction = adapter.predict(image_bytes)

    return {
        "inspection_id": req.inspection_id,
        **prediction,
        "latency_ms": LATENCY_MS,
    }


@app.post("/infer/ct")
def infer_ct(req: InferRequest) -> dict:
    return _infer(req, CT_ADAPTER)


@app.post("/infer/rgb")
def infer_rgb(req: InferRequest) -> dict:
    return _infer(req, RGB_ADAPTER)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "models": {
            "ct": True,
            "rgb": True,
        },
    }