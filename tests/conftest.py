import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture
def runtime(app):
    """앱이 들고 있는 런타임.

    이전에는 어댑터·설정·실행기가 `app.main` 의 모듈 전역이라 테스트가 그것을
    직접 monkeypatch 했다. 지금은 이 객체 하나만 바꿔 끼우면 된다.
    """
    return app.state.runtime


@pytest.fixture
def client(app):
    return TestClient(app)
