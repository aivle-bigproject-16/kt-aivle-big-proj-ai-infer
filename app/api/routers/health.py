"""준비 상태 엔드포인트.

어댑터가 하나라도 안 뜨면 프로세스가 죽는 대신 `degraded` 를 보고한다. 어느
모달이 왜 못 떴는지는 `details` 에 담긴다.
"""
from fastapi import APIRouter, Depends

from app.api.deps import get_runtime
from app.core.runtime import Runtime


router = APIRouter(tags=["ops"])


@router.get("/health", summary="서버 준비 상태와 모달별 어댑터 상세")
def health(runtime: Runtime = Depends(get_runtime)) -> dict:
    return runtime.health()
