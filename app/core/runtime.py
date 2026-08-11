"""추론 어댑터와 셀 분석 실행기를 담는 프로세스 런타임.

이전에는 이 상태가 `app.main` 의 모듈 전역이었다. 그래서 API 를 검토하거나
테스트하려면 모듈 전역을 monkeypatch 해야 했고, 라우트 정의와 모델 적재가 한
파일에 섞였다. 여기로 옮겨서 `app.api` 는 이 객체를 의존성으로 받기만 한다.
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore

from app.adapters.base import InferenceAdapter
from app.adapters.factory import build_adapter
from app.core.settings import Settings


logger = logging.getLogger(__name__)

MODALITIES = ("ct", "rgb")


class AdapterSlot:
    """어댑터 하나와, 그 어댑터를 못 만든 이유."""

    def __init__(
        self,
        adapter: InferenceAdapter | None,
        error: str | None,
    ):
        self.adapter = adapter
        self.error = error

    @property
    def ready(self) -> bool:
        return self.adapter is not None

    def detail(self) -> dict:
        if self.adapter is None:
            return {"adapter": None, "error": self.error}

        return {"adapter": type(self.adapter).__name__, "error": None}


def build_slot(modality: str, settings: Settings) -> AdapterSlot:
    """어댑터 생성 실패로 프로세스가 죽지 않게 한다.

    모델 파일이 없거나 세션 생성이 실패해도 서버는 뜨고, /health 가 사유를
    보고하며, 해당 모달 추론만 503 으로 거절한다.
    """
    try:
        return AdapterSlot(build_adapter(modality, settings), None)
    except Exception as exc:
        logger.exception("failed to build the %s adapter", modality)
        return AdapterSlot(None, f"{type(exc).__name__}: {exc}")


class Runtime:
    """앱이 살아 있는 동안 유지되는 상태 전부."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.slots: dict[str, AdapterSlot] = {
            modality: build_slot(modality, settings)
            for modality in MODALITIES
        }
        self.analysis_executor = ThreadPoolExecutor(
            max_workers=int(os.getenv("CELL_ANALYSIS_WORKERS", "1")),
            thread_name_prefix="cell-analysis",
        )
        self.analysis_capacity = BoundedSemaphore(
            settings.cell_analysis_queue_size
        )

    def slot(self, modality: str) -> AdapterSlot:
        return self.slots[modality]

    def cell_adapters(self) -> dict[str, InferenceAdapter | None]:
        """셀 분석 요청의 `imageType` 표기(대문자)로 어댑터를 찾게 한다."""
        return {
            modality.upper(): slot.adapter
            for modality, slot in self.slots.items()
        }

    def health(self) -> dict:
        details = {
            modality: slot.detail()
            for modality, slot in self.slots.items()
        }
        models = {
            modality: slot.ready
            for modality, slot in self.slots.items()
        }

        return {
            "status": "ok" if all(models.values()) else "degraded",
            "mode": self.settings.inference_mode,
            "models": models,
            "details": details,
        }
