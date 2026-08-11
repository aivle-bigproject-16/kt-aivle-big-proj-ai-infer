"""서비스 예외 → HTTP 상태 코드 매핑.

계약상 어떤 실패가 몇 번으로 나가는지는 **이 표가 유일한 근거**다. 라우트는
상태 코드를 직접 고르지 않는다.

| 예외 | 코드 | 상황 |
| --- | --- | --- |
| `ImageRejected` | 422 | 전처리가 이미지를 거부했다 |
| `InferenceFailed` | 500 | 추론 중 예기치 못한 실패 |
| `ImageDownloadError` | 502 | `image_url` 다운로드 실패 |
| `AdapterUnavailable` | 503 | 해당 모달 어댑터가 준비되지 않았다 |

`FAIL` 판정은 에러가 아니라 정상 200 응답이므로 여기 없다.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.download.http_image import ImageDownloadError
from app.services.inference import (
    AdapterUnavailable,
    ImageRejected,
    InferenceFailed,
)


# 예외 타입 → (상태 코드, 클라이언트에게 보일 detail).
# detail 이 None 이면 예외 메시지를 그대로 쓴다.
ERROR_MAP: list[tuple[type[Exception], int, str | None]] = [
    (ImageRejected, 422, "unprocessable inference image"),
    (InferenceFailed, 500, "inference failed"),
    (ImageDownloadError, 502, "failed to download inference image"),
    (AdapterUnavailable, 503, None),
]


def _handler(status_code: int, detail: str | None):
    async def handle(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"detail": detail if detail is not None else str(exc)},
        )

    return handle


def register_error_handlers(app: FastAPI) -> None:
    for exception_type, status_code, detail in ERROR_MAP:
        app.add_exception_handler(
            exception_type,
            _handler(status_code, detail),
        )
