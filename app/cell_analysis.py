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

DEFAULT_MIN_VALID_COVERAGE = 0.8
DEFAULT_RGB_CELL_REJECT_RATE_THRESHOLD = 0.7


# Proposed by infra and still awaiting formal backend confirmation. Keep the
# four situation-to-contract rows centralized here so callback behavior cannot
# drift independently across exception paths.
ASSUMED_BACKEND_CALLBACK_MAPPING = {
    "capture_or_quality_fail": {
        "cell_status": "FAILED",
        "failure_type": "CAPTURE",
    },
    "image_download_failure": {
        "cell_status": "FAILED",
        "failure_type": "AI",
    },
    "model_load_or_inference_failure": {
        "cell_status": "FAILED",
        "failure_type": "AI",
    },
    "normal_completion": {
        "cell_status": "COMPLETED",
        "failure_type": None,
    },
}


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


def _final_label(
    results: list[ImageAnalysisResult],
    rgb_reject_rate_threshold: float,
) -> str:
    for image_type in {result.image_type for result in results}:
        modality_results = [
            result for result in results if result.image_type == image_type
        ]
        reject_count = sum(
            result.label == "REJECT" for result in modality_results
        )
        if image_type == "RGB":
            if reject_count / len(modality_results) >= rgb_reject_rate_threshold:
                return "REJECT"
        elif reject_count:
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


def _quality_label(result: ImageAnalysisResult) -> str:
    if result.raw_response:
        quality = result.raw_response.get("quality")
        if isinstance(quality, dict) and quality.get("label") in {
            "PASS",
            "FAIL",
        }:
            if quality.get("gateMode") == "shadow":
                return "PASS"
            return quality["label"]
    return "FAIL" if result.label == "FAIL" else "PASS"


def _modality_coverage(
    results: list[ImageAnalysisResult],
) -> dict[str, tuple[int, int]]:
    coverage: dict[str, tuple[int, int]] = {}
    for image_type in sorted({result.image_type for result in results}):
        modality_results = [
            result for result in results if result.image_type == image_type
        ]
        valid = sum(
            _quality_label(result) == "PASS"
            for result in modality_results
        )
        coverage[image_type] = (valid, len(modality_results))
    return coverage


def _has_insufficient_coverage(
    results: list[ImageAnalysisResult],
    minimum_valid_coverage: float,
) -> bool:
    return any(
        total == 0 or valid / total < minimum_valid_coverage
        for valid, total in _modality_coverage(results).values()
    )


def _callback_situation(
    results: list[ImageAnalysisResult],
    minimum_valid_coverage: float,
) -> str:
    if any(
        result.error_code == "IMAGE_DOWNLOAD_FAILED" for result in results
    ):
        return "image_download_failure"
    if any(result.error_code for result in results):
        return "model_load_or_inference_failure"
    if _has_insufficient_coverage(results, minimum_valid_coverage):
        return "capture_or_quality_fail"
    return "normal_completion"


def _failure_reason(
    situation: str,
    results: list[ImageAnalysisResult],
) -> str | None:
    if situation == "normal_completion":
        return None
    if situation == "capture_or_quality_fail":
        summaries = []
        for image_type, (valid, total) in _modality_coverage(results).items():
            failed_count = total - valid
            summaries.append(
                f"{image_type} valid coverage {valid}/{total} "
                f"({valid / total:.2%}); "
                f"failedCount={failed_count}"
            )
        return " | ".join(summaries)
    return "; ".join(
        f"image {result.image_id}: {result.error_code}"
        for result in results
        if result.error_code
    )


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
        if isinstance(exc, ImageDownloadError):
            error_code = "IMAGE_DOWNLOAD_FAILED"
        elif isinstance(exc, (TimeoutError, httpx.TimeoutException)):
            error_code = "INFERENCE_TIMEOUT"
        elif isinstance(exc, MemoryError) or any(
            marker in str(exc).lower()
            for marker in (
                "out of memory",
                "resource exhausted",
                "cuda error: out of memory",
            )
        ):
            error_code = "INFERENCE_RESOURCE_EXHAUSTED"
        else:
            error_code = "INFERENCE_FAILED"
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
    minimum_valid_coverage: float = (
        DEFAULT_MIN_VALID_COVERAGE
    ),
    rgb_reject_rate_threshold: float = (
        DEFAULT_RGB_CELL_REJECT_RATE_THRESHOLD
    ),
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

    situation = _callback_situation(
        results,
        minimum_valid_coverage,
    )
    contract = ASSUMED_BACKEND_CALLBACK_MAPPING[situation]
    cell_status = contract["cell_status"]
    failure_type = contract["failure_type"]
    final_label = (
        _final_label(results, rgb_reject_rate_threshold)
        if situation == "normal_completion"
        else None
    )
    confidence = _cell_confidence(final_label or "FAIL", results)
    failure_reason = _failure_reason(situation, results)

    from datetime import datetime, timezone

    return CellAnalysisCallback(
        request_id=request.request_id,
        batch_id=request.batch_id,
        inspection_id=request.inspection_id,
        battery_cell_id=request.battery_cell_id,
        cell_serial_no=request.cell_serial_no,
        cell_status=cell_status,
        final_label=final_label,
        failure_type=failure_type,
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
    minimum_valid_coverage: float = (
        DEFAULT_MIN_VALID_COVERAGE
    ),
    rgb_reject_rate_threshold: float = (
        DEFAULT_RGB_CELL_REJECT_RATE_THRESHOLD
    ),
) -> None:
    callback = build_callback(
        request,
        adapters,
        minimum_valid_coverage,
        rgb_reject_rate_threshold,
    )
    send_callback(
        request.callback_url,
        callback,
        internal_api_key,
        callback_timeout_seconds,
        callback_max_attempts,
    )
