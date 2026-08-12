import logging
from time import perf_counter, sleep

import httpx

from app.adapters.base import InferenceAdapter
from app.download.http_image import ImageDownloadError
from app.download.s3_image import download_s3_image
from app.schemas import (
    CallbackDefect,
    CellAnalysisCallback,
    CellAnalysisRequest,
    ImageAnalysisResult,
)


logger = logging.getLogger(__name__)


def _callback_defects(defects: list[dict]) -> list[CallbackDefect]:
    converted = []
    for defect in defects:
        bbox = defect["bbox"]
        converted.append(CallbackDefect(
            defect_type=defect["defectType"],
            confidence=defect["confidence"],
            bbox={
                "x": round(bbox["x"]),
                "y": round(bbox["y"]),
                "width": max(0, round(bbox["width"])),
                "height": max(0, round(bbox["height"])),
            },
        ))
    return converted


def _final_label(results: list[ImageAnalysisResult]) -> str:
    labels = {result.label for result in results}
    if "FAIL" in labels:
        return "FAIL"
    if "REJECT" in labels:
        return "REJECT"
    return "PASS"


def _cell_confidence(
    final_label: str,
    results: list[ImageAnalysisResult],
) -> float:
    decisive = [
        result.confidence
        for result in results
        if result.label == final_label
    ]
    if not decisive:
        return 0.0
    if final_label == "PASS":
        return min(decisive)
    return max(decisive)


def _analyze_image(image, adapter: InferenceAdapter) -> ImageAnalysisResult:
    started_at = perf_counter()
    try:
        image_bytes = download_s3_image(image.bucket_name, image.object_key)
        prediction = adapter.predict(image_bytes)
        latency_ms = max(0, round((perf_counter() - started_at) * 1000))
        return ImageAnalysisResult(
            image_id=image.image_id,
            image_type=image.image_type,
            label=prediction["label"],
            confidence=prediction["confidence"],
            defects=_callback_defects(prediction.get("defects", [])),
            raw_response=prediction,
            latency_ms=latency_ms,
            error_code=None,
            error_message=None,
        )
    except Exception as exc:
        latency_ms = max(0, round((perf_counter() - started_at) * 1000))
        logger.exception("image analysis failed for image %s", image.image_id)
        error_code = (
            "IMAGE_DOWNLOAD_FAILED"
            if isinstance(exc, ImageDownloadError)
            else "INFERENCE_FAILED"
        )
        return ImageAnalysisResult(
            image_id=image.image_id,
            image_type=image.image_type,
            label="FAIL",
            confidence=0.0,
            defects=[],
            raw_response=None,
            latency_ms=latency_ms,
            error_code=error_code,
            error_message=str(exc) or type(exc).__name__,
        )


def build_callback(
    request: CellAnalysisRequest,
    adapters: dict[str, InferenceAdapter | None],
) -> CellAnalysisCallback:
    results: list[ImageAnalysisResult] = []
    for image in request.images:
        adapter = adapters.get(image.image_type)
        if adapter is None:
            results.append(ImageAnalysisResult(
                image_id=image.image_id,
                image_type=image.image_type,
                label="FAIL",
                confidence=0.0,
                defects=[],
                raw_response=None,
                latency_ms=0,
                error_code="ADAPTER_UNAVAILABLE",
                error_message=f"{image.image_type} adapter is unavailable",
            ))
            continue
        results.append(_analyze_image(image, adapter))

    failed = [result for result in results if result.error_code]
    cell_status = "FAILED" if failed else "COMPLETED"
    final_label = "FAIL" if failed else _final_label(results)
    confidence = _cell_confidence(final_label, results)
    failure_reason = (
        "; ".join(
            f"image {result.image_id}: {result.error_code}"
            for result in failed
        )
        or None
    )

    from datetime import datetime, timezone

    return CellAnalysisCallback(
        request_id=request.request_id,
        batch_id=request.batch_id,
        inspection_id=request.inspection_id,
        battery_cell_id=request.battery_cell_id,
        cell_serial_no=request.cell_serial_no,
        cell_status=cell_status,
        final_label=final_label,
        failure_reason=failure_reason,
        confidence=confidence,
        completed_at=datetime.now(timezone.utc),
        image_results=results,
    )


def send_callback(
    callback_url: str,
    callback: CellAnalysisCallback,
    internal_api_key: str,
    timeout_seconds: float,
    max_attempts: int,
) -> None:
    headers = {"X-Internal-Api-Key": internal_api_key}
    payload = callback.model_dump(mode="json", by_alias=True)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = httpx.post(
                callback_url,
                json=payload,
                headers=headers,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            return
        except httpx.HTTPError as exc:
            last_error = exc
            logger.warning(
                "callback attempt %s/%s failed for request %s: %s",
                attempt,
                max_attempts,
                callback.request_id,
                exc,
            )
            if attempt < max_attempts:
                sleep(min(2 ** (attempt - 1), 5))

    raise RuntimeError("backend callback delivery failed") from last_error


def process_cell_analysis(
    request: CellAnalysisRequest,
    adapters: dict[str, InferenceAdapter | None],
    internal_api_key: str,
    callback_timeout_seconds: float,
    callback_max_attempts: int,
) -> None:
    callback = build_callback(request, adapters)
    send_callback(
        request.callback_url,
        callback,
        internal_api_key,
        callback_timeout_seconds,
        callback_max_attempts,
    )
