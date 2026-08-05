import os
import random
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


class StubAdapter:
    def __init__(self, modality: str):
        if modality not in {"ct", "rgb"}:
            raise ValueError(f"unsupported modality: {modality}")

        self.modality = modality
        self.reject_rate = REJECT_RATE
        self.fail_rate = FAIL_RATE

    def predict(self, image_bytes: bytes) -> dict:
        if not image_bytes:
            raise ValueError("image_bytes must not be empty")

        if random.random() < self.fail_rate:
            return {
                "label": "FAIL",
                "confidence": 0.0,
                "defects": [],
            }

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