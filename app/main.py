"""앱 조립.

이 파일은 배선만 한다 — 라우트 본문, 상태 코드, 스키마, 모델 적재는 전부 다른
모듈에 있다. 엔드포인트를 검토하려면 `app/api/` 를 본다.
"""
from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routers import ROUTERS
from app.core.runtime import Runtime
from app.core.settings import load_settings


def create_app(runtime: Runtime | None = None) -> FastAPI:
    """앱 인스턴스를 만든다.

    `runtime` 을 넘기면 그 런타임을 쓴다. 테스트가 모델을 적재하지 않고 앱을
    세울 때 쓰는 통로다.
    """
    app = FastAPI(
        title="ai-infer",
        summary="KT AIVLE 빅프로젝트 16조 AI 추론 서버",
    )
    app.state.runtime = runtime if runtime is not None else Runtime(
        load_settings()
    )

    for router in ROUTERS:
        app.include_router(router)

    register_error_handlers(app)

    return app


app = create_app()
