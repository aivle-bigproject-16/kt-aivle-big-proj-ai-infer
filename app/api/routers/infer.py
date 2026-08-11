"""단건 추론 엔드포인트.

BE 가 발급한 presigned URL 을 받아 이미지 한 장을 판정하고 동기로 답한다.
배치 오케스트레이션과 셀 판정 저장은 BE 책임이다.
"""
from fastapi import APIRouter, Depends

from app.api.deps import get_ct_slot, get_rgb_slot, get_settings
from app.api.schemas.infer import InferRequest, InferResponse
from app.core.runtime import AdapterSlot
from app.core.settings import Settings
from app.services.inference import run_inference


router = APIRouter(tags=["inference"])

# 계약상 발생 가능한 실패. 근거는 app/api/errors.py 의 표다.
INFER_RESPONSES = {
    422: {"description": "전처리가 이미지를 거부했습니다"},
    500: {"description": "추론 중 예기치 못한 실패"},
    502: {"description": "image_url 다운로드 실패"},
    503: {"description": "해당 모달 어댑터가 준비되지 않았습니다"},
}


def _infer(
    req: InferRequest,
    slot: AdapterSlot,
    settings: Settings,
) -> dict:
    return run_inference(
        adapter=slot.adapter,
        adapter_error=slot.error,
        image_url=req.image_url,
        inspection_id=req.inspection_id,
        stub_mode=settings.inference_mode == "stub",
    )


@router.post(
    "/infer/ct",
    response_model=InferResponse,
    responses=INFER_RESPONSES,
    summary="CT 이미지 1장 추론",
)
def infer_ct(
    req: InferRequest,
    slot: AdapterSlot = Depends(get_ct_slot),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _infer(req, slot, settings)


@router.post(
    "/infer/rgb",
    response_model=InferResponse,
    responses=INFER_RESPONSES,
    summary="RGB 이미지 1장 추론",
)
def infer_rgb(
    req: InferRequest,
    slot: AdapterSlot = Depends(get_rgb_slot),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _infer(req, slot, settings)
