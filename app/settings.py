import os
from dataclasses import dataclass

from app.adapters.ct_defect_onnx import DEFAULT_CONF_THRESHOLD
from app.adapters.ct_quality_onnx import DEFAULT_THRESHOLD as CT_QUALITY_THRESHOLD
from app.adapters.rgb_quality_onnx import FAIL_THRESHOLD as RGB_QUALITY_FAIL_THRESHOLD


@dataclass(frozen=True)
class Settings:
    inference_mode: str
    onnx_device: str
    ct_quality_model_path: str
    ct_defect_model_path: str
    rgb_quality_model_path: str
    rgb_defect_model_dir: str
    ct_postprocess_type: str
    ct_postprocess_match_metric: str
    ct_postprocess_match_threshold: float
    internal_api_key: str = ""
    callback_timeout_seconds: float = 10.0
    callback_max_attempts: int = 3
    backend_callback_url: str = ""
    cell_analysis_queue_size: int = 4
    ct_defect_conf_threshold: float = DEFAULT_CONF_THRESHOLD
    ct_quality_threshold: float = CT_QUALITY_THRESHOLD
    rgb_quality_fail_threshold: float = RGB_QUALITY_FAIL_THRESHOLD
    cell_min_valid_coverage: float = 0.8
    rgb_cell_reject_rate_threshold: float = 0.7
    ct_quality_gate_mode: str = "enforce"


def _float_env(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _unit_interval_env(name: str, default: float) -> float:
    value = _float_env(name, default)

    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")

    return value


def _positive_int_env(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _positive_float_env(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if not 0.0 < value < float("inf"):
        raise ValueError(f"{name} must be finite and greater than 0")
    return value


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

    onnx_device = os.getenv("ONNX_DEVICE", "cpu").strip().lower()
    if onnx_device not in {"cpu", "cuda"}:
        raise ValueError("ONNX_DEVICE must be cpu or cuda")

    ct_postprocess_match_metric = os.getenv(
        "CT_POSTPROCESS_MATCH_METRIC",
        "IOS",
    ).strip().upper()
    if ct_postprocess_match_metric not in {"IOU", "IOS"}:
        raise ValueError(
            "CT_POSTPROCESS_MATCH_METRIC must be IOU or IOS"
        )

    ct_postprocess_match_threshold = _unit_interval_env(
        "CT_POSTPROCESS_MATCH_THRESHOLD",
        0.44,
    )
    ct_defect_conf_threshold = _unit_interval_env(
        "CT_DEFECT_CONF_THRESHOLD",
        DEFAULT_CONF_THRESHOLD,
    )
    rgb_quality_fail_threshold = _unit_interval_env(
        "RGB_QUALITY_FAIL_THRESHOLD",
        RGB_QUALITY_FAIL_THRESHOLD,
    )
    cell_min_valid_coverage = _unit_interval_env(
        "CELL_MIN_VALID_COVERAGE",
        0.8,
    )
    if cell_min_valid_coverage == 0.0:
        raise ValueError(
            "CELL_MIN_VALID_COVERAGE must be greater than 0"
        )
    rgb_cell_reject_rate_threshold = _unit_interval_env(
        "RGB_CELL_REJECT_RATE_THRESHOLD",
        0.7,
    )
    if rgb_cell_reject_rate_threshold == 0.0:
        raise ValueError(
            "RGB_CELL_REJECT_RATE_THRESHOLD must be greater than 0"
        )
    ct_quality_gate_mode = os.getenv(
        "CT_QUALITY_GATE_MODE",
        "enforce",
    ).strip().lower()
    if ct_quality_gate_mode not in {"enforce", "shadow"}:
        raise ValueError(
            "CT_QUALITY_GATE_MODE must be enforce or shadow"
        )
    # CT 품질 모델은 확률이 아니라 로짓을 비교하므로 [0,1] 제약을 걸지 않는다.
    ct_quality_threshold = _float_env(
        "CT_QUALITY_THRESHOLD",
        CT_QUALITY_THRESHOLD,
    )

    return Settings(
        inference_mode=mode,
        onnx_device=onnx_device,
        ct_quality_model_path=os.getenv(
            "CT_QUALITY_MODEL_PATH",
            "/models/quality_ct.onnx",
        ),
        ct_defect_model_path=os.getenv(
            "CT_DEFECT_MODEL_PATH",
            "/models/defect_ct.onnx",
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
        internal_api_key=os.getenv("AI_INTERNAL_API_KEY", ""),
        callback_timeout_seconds=_positive_float_env(
            "CALLBACK_TIMEOUT_SECONDS",
            10.0,
        ),
        callback_max_attempts=_positive_int_env(
            "CALLBACK_MAX_ATTEMPTS",
            3,
        ),
        backend_callback_url=os.getenv("BACKEND_CALLBACK_URL", ""),
        cell_analysis_queue_size=_positive_int_env(
            "CELL_ANALYSIS_QUEUE_SIZE",
            4,
        ),
        ct_defect_conf_threshold=ct_defect_conf_threshold,
        ct_quality_threshold=ct_quality_threshold,
        rgb_quality_fail_threshold=rgb_quality_fail_threshold,
        cell_min_valid_coverage=cell_min_valid_coverage,
        rgb_cell_reject_rate_threshold=(
            rgb_cell_reject_rate_threshold
        ),
        ct_quality_gate_mode=ct_quality_gate_mode,
    )
