"""라우트가 쓰는 의존성.

런타임 상태를 여기 한 곳에서만 꺼낸다. 라우트 함수는 모듈 전역을 읽지 않으므로,
테스트는 `runtime` 객체만 바꿔 끼우면 된다.
"""
import secrets

from fastapi import Depends, Header, HTTPException, Request

from app.core.runtime import AdapterSlot, Runtime
from app.core.settings import Settings


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_settings(runtime: Runtime = Depends(get_runtime)) -> Settings:
    return runtime.settings


def get_ct_slot(runtime: Runtime = Depends(get_runtime)) -> AdapterSlot:
    return runtime.slot("ct")


def get_rgb_slot(runtime: Runtime = Depends(get_runtime)) -> AdapterSlot:
    return runtime.slot("rgb")


def require_internal_api_key(
    x_internal_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """BE 내부 호출임을 확인한다.

    키가 설정돼 있지 않으면 어떤 요청도 통과시키지 않는다. 비교는 타이밍 공격을
    막기 위해 `secrets.compare_digest` 로 한다.
    """
    if (
        not settings.internal_api_key
        or not x_internal_api_key
        or not secrets.compare_digest(
            x_internal_api_key,
            settings.internal_api_key,
        )
    ):
        raise HTTPException(status_code=401, detail="unauthorized")
