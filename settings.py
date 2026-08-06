import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    inference_mode: str
    ct_quality_model_path: str
    ct_defect_model_path: str
    rgb_quality_model_path: str


def load_settings() -> Settings:
    mode = os.getenv("INFERENCE_MODE", "stub").strip().lower()
    allowed_modes = {"stub", "ct-quality-onnx", "onnx"}

    if mode not in allowed_modes:
        raise ValueError(
            "INFERENCE_MODE must be stub, ct-quality-onnx, or onnx"
        )

    return Settings(
        inference_mode=mode,
        ct_quality_model_path=os.getenv(
            "CT_QUALITY_MODEL_PATH",
            "/models/quality_ct.onnx",
        ),
        ct_defect_model_path=os.getenv(
            "CT_DEFECT_MODEL_PATH",
            "/models/detect_ct.onnx",
        ),
        rgb_quality_model_path=os.getenv(
            "RGB_QUALITY_MODEL_PATH",
            "/models/quality_rgb.onnx",
        ),
    )
