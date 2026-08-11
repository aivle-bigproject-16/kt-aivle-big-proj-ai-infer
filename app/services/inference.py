"""이미지 한 장을 판정하는 유스케이스.

라우트가 아니라 여기서 다운로드·추론·지연시간 측정을 한다. 실패는 HTTP 상태가
아니라 이 모듈의 예외로 표현하고, 상태 코드 매핑은 `app.api.errors` 가 맡는다.
"""
import logging
import os
from time import perf_counter, sleep

from app.adapters.base import InferenceAdapter
from app.download.http_image import ImageDownloadError, download_image


logger = logging.getLogger(__name__)

# 스텁 모드에서만 쓰는 인위적 지연. 실모델 경로에는 적용하지 않는다.
LATENCY_MS = int(os.getenv("STUB_LATENCY_MS", "800"))


class AdapterUnavailable(RuntimeError):
    """해당 모달 어댑터가 뜨지 않았다. 요청은 처리할 수 없다."""


class ImageRejected(ValueError):
    """전처리가 이미지를 거부했다. 서버 잘못이 아니다."""


class InferenceFailed(RuntimeError):
    """추론 도중 예기치 못한 실패가 났다."""


def run_inference(
    adapter: InferenceAdapter | None,
    adapter_error: str | None,
    image_url: str,
    inspection_id: int,
    stub_mode: bool,
) -> dict:
    if adapter is None:
        raise AdapterUnavailable(
            f"inference adapter is unavailable: {adapter_error}"
        )

    started_at = perf_counter()

    image_bytes = download_image(image_url)

    if stub_mode:
        sleep(LATENCY_MS / 1000)

    try:
        prediction = adapter.predict(image_bytes)
    except ValueError as exc:
        raise ImageRejected("unprocessable inference image") from exc
    except Exception as exc:
        logger.exception("inference failed for inspection %s", inspection_id)
        raise InferenceFailed("inference failed") from exc

    latency_ms = max(
        0,
        round((perf_counter() - started_at) * 1000),
    )

    return {
        "inspection_id": inspection_id,
        **prediction,
        "latency_ms": latency_ms,
    }


__all__ = [
    "AdapterUnavailable",
    "ImageDownloadError",
    "ImageRejected",
    "InferenceFailed",
    "run_inference",
]
