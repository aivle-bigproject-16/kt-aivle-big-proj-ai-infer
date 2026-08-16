import os
import random
from time import perf_counter
from typing import Protocol


REJECT_RATE = float(os.getenv("STUB_REJECT_RATE", "0.3"))
FAIL_RATE = float(os.getenv("STUB_FAIL_RATE", "0.0"))

if not 0.0 <= REJECT_RATE <= 1.0:
    raise ValueError("STUB_REJECT_RATE must be between 0.0 and 1.0")

if not 0.0 <= FAIL_RATE <= 1.0:
    raise ValueError("STUB_FAIL_RATE must be between 0.0 and 1.0")


class InferenceAdapter(Protocol):
    def predict(self, image_bytes: bytes) -> dict:
        ...


class QualityAdapter(Protocol):
    def predict_quality(self, image_bytes: bytes) -> dict:
        ...


class DefectAdapter(Protocol):
    def predict_defects(self, image_bytes: bytes) -> dict:
        ...


class StubQualityAdapter:
    def __init__(self, fail_rate: float = FAIL_RATE):
        self.fail_rate = fail_rate

    def predict_quality(self, image_bytes: bytes) -> dict:
        if not image_bytes:
            raise ValueError("image_bytes must not be empty")

        if random.random() < self.fail_rate:
            return {
                "label": "FAIL",
                "confidence": 0.0,
            }

        return {
            "label": "PASS",
            "confidence": 1.0,
        }


class StubDefectAdapter:
    def __init__(
        self,
        modality: str,
        reject_rate: float = REJECT_RATE,
    ):
        if modality not in {"ct", "rgb"}:
            raise ValueError(f"unsupported modality: {modality}")

        self.modality = modality
        self.reject_rate = reject_rate

    def predict_defects(self, image_bytes: bytes) -> dict:
        if not image_bytes:
            raise ValueError("image_bytes must not be empty")

        if random.random() >= self.reject_rate:
            return {
                "label": "PASS",
                "confidence": 1.0,
                "defects": [],
            }

        allowed_types = (
            ["MICRO_DEFECT"]
            if self.modality == "ct"
            else ["CRACK", "SPOT"]
        )

        return {
            "label": "REJECT",
            "confidence": round(random.uniform(0.75, 0.99), 4),
            "defects": [
                {
                    "defectType": random.choice(allowed_types),
                    "confidence": round(
                        random.uniform(0.75, 0.99),
                        4,
                    ),
                    "bbox": {
                        "x": 120.0,
                        "y": 80.0,
                        "width": 240.0,
                        "height": 160.0,
                    },
                }
            ],
        }


class InferencePipeline:
    def __init__(
        self,
        quality_adapter: QualityAdapter,
        defect_adapter: DefectAdapter,
        quality_gate_mode: str = "enforce",
    ):
        if quality_gate_mode not in {"enforce", "shadow"}:
            raise ValueError(
                "quality_gate_mode must be enforce or shadow"
            )
        self.quality_adapter = quality_adapter
        self.defect_adapter = defect_adapter
        self.quality_gate_mode = quality_gate_mode

    def predict(self, image_bytes: bytes) -> dict:
        prediction, _ = self.predict_with_timings(image_bytes)
        return prediction

    def predict_with_timings(
        self,
        image_bytes: bytes,
    ) -> tuple[dict, dict[str, int]]:
        pipeline_started_at = perf_counter()
        quality_started_at = perf_counter()
        quality = self.quality_adapter.predict_quality(image_bytes)
        quality_ms = max(
            0,
            round((perf_counter() - quality_started_at) * 1000),
        )

        quality_observation = {
            **quality,
            "gateMode": self.quality_gate_mode,
        }

        if (
            quality["label"] == "FAIL"
            and self.quality_gate_mode == "enforce"
        ):
            prediction = {
                "label": "FAIL",
                "confidence": quality["confidence"],
                "defects": [],
                "quality": quality_observation,
            }
            timings = {
                "quality_ms": quality_ms,
                "pipeline_ms": max(
                    0,
                    round((perf_counter() - pipeline_started_at) * 1000),
                ),
            }
            return prediction, timings

        defect_started_at = perf_counter()
        prediction = self.defect_adapter.predict_defects(image_bytes)
        prediction = {
            **prediction,
            "quality": quality_observation,
        }
        defect_ms = max(
            0,
            round((perf_counter() - defect_started_at) * 1000),
        )
        timings = {
            "quality_ms": quality_ms,
            "defect_ms": defect_ms,
            "pipeline_ms": max(
                0,
                round((perf_counter() - pipeline_started_at) * 1000),
            ),
        }
        return prediction, timings


class StubAdapter:
    """Compatibility facade over the split stub pipeline."""

    def __init__(self, modality: str):
        self.quality_adapter = StubQualityAdapter()
        self.defect_adapter = StubDefectAdapter(modality)
        self.pipeline = InferencePipeline(
            quality_adapter=self.quality_adapter,
            defect_adapter=self.defect_adapter,
        )

    @property
    def fail_rate(self) -> float:
        return self.quality_adapter.fail_rate

    @fail_rate.setter
    def fail_rate(self, value: float) -> None:
        self.quality_adapter.fail_rate = value

    @property
    def reject_rate(self) -> float:
        return self.defect_adapter.reject_rate

    @reject_rate.setter
    def reject_rate(self, value: float) -> None:
        self.defect_adapter.reject_rate = value

    def predict(self, image_bytes: bytes) -> dict:
        return self.pipeline.predict(image_bytes)

    def predict_with_timings(
        self,
        image_bytes: bytes,
    ) -> tuple[dict, dict[str, int]]:
        return self.pipeline.predict_with_timings(image_bytes)
