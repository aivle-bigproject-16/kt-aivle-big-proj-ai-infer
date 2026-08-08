import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    inference_mode: str
    ct_quality_model_path: str
    ct_defect_model_path: str
    rgb_quality_model_path: str
    rgb_defect_model_dir: str
    ct_postprocess_type: str
    ct_postprocess_match_metric: str
    ct_postprocess_match_threshold: float


def load_settings() -> Settings:
    mode = os.getenv("INFERENCE_MODE", "stub").strip().lower()
    allowed_modes = {
        "stub",
        "ct-quality-onnx",
        "ct-onnx",
        "quality-onnx",
        "rgb-onnx",
        "onnx",
    }

    if mode not in allowed_modes:
        raise ValueError(
            "INFERENCE_MODE must be stub, ct-quality-onnx, ct-onnx, "
            "quality-onnx, rgb-onnx, or onnx"
        )

    ct_postprocess_type = os.getenv(
        "CT_POSTPROCESS_TYPE",
        "NMS",
    ).strip().upper()
    if ct_postprocess_type not in {"NMS", "GREEDYNMM"}:
        raise ValueError(
            "CT_POSTPROCESS_TYPE must be NMS or GREEDYNMM"
        )

    ct_postprocess_match_metric = os.getenv(
        "CT_POSTPROCESS_MATCH_METRIC",
        "IOS",
    ).strip().upper()
    if ct_postprocess_match_metric not in {"IOU", "IOS"}:
        raise ValueError(
            "CT_POSTPROCESS_MATCH_METRIC must be IOU or IOS"
        )

    ct_postprocess_match_threshold = float(
        os.getenv("CT_POSTPROCESS_MATCH_THRESHOLD", "0.44")
    )
    if not 0.0 <= ct_postprocess_match_threshold <= 1.0:
        raise ValueError(
            "CT_POSTPROCESS_MATCH_THRESHOLD must be between 0.0 and 1.0"
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
        rgb_defect_model_dir=os.getenv(
            "RGB_DEFECT_MODEL_DIR",
            "/models/rgb_owlv2_onnx",
        ),
        ct_postprocess_type=ct_postprocess_type,
        ct_postprocess_match_metric=ct_postprocess_match_metric,
        ct_postprocess_match_threshold=ct_postprocess_match_threshold,
    )
