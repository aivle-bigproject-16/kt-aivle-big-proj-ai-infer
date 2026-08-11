"""셀 단위 비동기 분석 엔드포인트.

BE 가 셀 하나(이미지 여러 장)를 맡기면 즉시 `202 Accepted` 로 답하고, 백그라운드
스레드가 S3 에서 이미지를 읽어 추론한 뒤 BE 콜백 URL 로 결과를 POST 한다.
"""
import logging
from datetime import datetime, timezone
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_runtime, get_settings, require_internal_api_key
from app.api.schemas.cells import (
    CellAnalysisAccepted,
    CellAnalysisCallback,
    CellAnalysisRequest,
)
from app.core.runtime import Runtime
from app.core.settings import Settings
from app.services.cell_analysis import process_cell_analysis


logger = logging.getLogger(__name__)

router = APIRouter(tags=["cell-analysis"])

# 서버가 BE 로 **보내는** 요청이라 응답 모델로는 안 잡힌다. OpenAPI callbacks 로
# 선언해 두면 BE 가 docs/openapi.json 하나로 양방향 계약을 다 볼 수 있다.
callback_router = APIRouter()


@callback_router.post(
    "{$request.body.callbackUrl}",
    summary="분석 완료 후 서버가 BE 로 보내는 콜백",
)
def cell_analysis_callback(body: CellAnalysisCallback) -> None:
    """`X-Internal-Api-Key` 를 함께 보낸다. BE 는 2xx 로 답해야 한다.

    2xx 가 아니면 `CALLBACK_MAX_ATTEMPTS` 까지 지수 백오프로 재시도한다.
    """


def _analysis_finished(runtime: Runtime, future) -> None:
    runtime.analysis_capacity.release()
    error = future.exception()
    if error is not None:
        logger.error(
            "cell analysis background task failed",
            exc_info=(type(error), error, error.__traceback__),
        )


@router.post(
    "/ai/cells/analyze",
    response_model=CellAnalysisAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_api_key)],
    callbacks=callback_router.routes,
    responses={
        400: {"description": "callbackUrl 이 설정된 콜백과 다릅니다"},
        401: {"description": "X-Internal-Api-Key 불일치"},
        503: {"description": "셀 분석 큐가 가득 찼습니다"},
    },
    summary="셀 1개 비동기 분석 접수",
)
def analyze_cell(
    req: CellAnalysisRequest,
    runtime: Runtime = Depends(get_runtime),
    settings: Settings = Depends(get_settings),
) -> CellAnalysisAccepted:
    # 콜백 목적지는 설정값과 정확히 일치해야 한다. 요청이 부르는 대로 따라가면
    # 인증된 호출자가 결과를 임의 주소로 흘릴 수 있다.
    if (
        not settings.backend_callback_url
        or req.callback_url != settings.backend_callback_url
    ):
        raise HTTPException(
            status_code=400,
            detail="callbackUrl does not match configured backend callback",
        )

    if not runtime.analysis_capacity.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail="cell analysis queue is full",
        )

    try:
        future = runtime.analysis_executor.submit(
            partial(
                process_cell_analysis,
                req,
                runtime.cell_adapters(),
                settings.internal_api_key,
                settings.callback_timeout_seconds,
                settings.callback_max_attempts,
            )
        )
    except Exception:
        runtime.analysis_capacity.release()
        raise
    future.add_done_callback(partial(_analysis_finished, runtime))

    return CellAnalysisAccepted(
        accepted=True,
        request_id=req.request_id,
        inspection_id=req.inspection_id,
        battery_cell_id=req.battery_cell_id,
        status="ACCEPTED",
        accepted_at=datetime.now(timezone.utc),
    )
