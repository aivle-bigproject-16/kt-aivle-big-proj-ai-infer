from collections.abc import Callable

from app.adapters.base import (
    InferenceAdapter,
    InferencePipeline,
    StubAdapter,
    StubDefectAdapter,
    StubQualityAdapter,
)
from app.adapters.ct_quality_onnx import OnnxCtQualityAdapter
from app.adapters.rgb_quality_onnx import OnnxRgbQualityAdapter
from app.adapters.ct_defect_onnx import OnnxCtDefectAdapter
from app.settings import Settings


MODALITIES = ("ct", "rgb")

# 모드 → 모달별로 실모델을 쓰는 단계. 여기 없는 단계는 스텁이 맡는다.
#   quality = 촬영불량 분류기(T-3), defect = 결함 검출
MODE_PLAN: dict[str, dict[str, set[str]]] = {
    "stub": {"ct": set(), "rgb": set()},
    "ct-quality-onnx": {"ct": {"quality"}, "rgb": set()},
    "quality-onnx": {"ct": {"quality"}, "rgb": {"quality"}},
    "ct-onnx": {"ct": {"quality", "defect"}, "rgb": set()},
    "rgb-onnx": {"ct": set(), "rgb": {"quality", "defect"}},
    "onnx": {
        "ct": {"quality", "defect"},
        "rgb": {"quality", "defect"},
    },
}


def _onnx_providers(device: str) -> list[str]:
    if device == "cuda":
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def _build_ct_quality(settings: Settings):
    return OnnxCtQualityAdapter(
        settings.ct_quality_model_path,
        threshold=settings.ct_quality_threshold,
        providers=_onnx_providers(settings.onnx_device),
    )


def _build_rgb_quality(settings: Settings):
    return OnnxRgbQualityAdapter(
        settings.rgb_quality_model_path,
        fail_threshold=settings.rgb_quality_fail_threshold,
        providers=_onnx_providers(settings.onnx_device),
    )


def _build_ct_defect(settings: Settings):
    return OnnxCtDefectAdapter(
        settings.ct_defect_model_path,
        postprocess_type=settings.ct_postprocess_type,
        postprocess_match_metric=(
            settings.ct_postprocess_match_metric
        ),
        postprocess_match_threshold=(
            settings.ct_postprocess_match_threshold
        ),
        conf_threshold=settings.ct_defect_conf_threshold,
        device=(
            "cuda:0"
            if settings.onnx_device == "cuda"
            else "cpu"
        ),
    )


def _build_rgb_defect(settings: Settings):
    try:
        from app.adapters.rgb_defect_owlv2 import (
            build_rgb_owlv2_onnx_defect_adapter,
        )
    except ImportError as exc:  # pragma: no cover - 이미지 구성 오류
        raise RuntimeError(
            "RGB defect model dependencies are missing. The CPU image "
            "ships stub and CT inference only; run RGB modes on the GPU "
            "image built from docker/Dockerfile.gpu-onnx."
        ) from exc

    return build_rgb_owlv2_onnx_defect_adapter(
        settings.rgb_defect_model_dir,
        providers=_onnx_providers(settings.onnx_device),
    )


_QUALITY_BUILDERS: dict[str, Callable[[Settings], object]] = {
    "ct": _build_ct_quality,
    "rgb": _build_rgb_quality,
}

_DEFECT_BUILDERS: dict[str, Callable[[Settings], object]] = {
    "ct": _build_ct_defect,
    "rgb": _build_rgb_defect,
}


def build_adapter(
    modality: str,
    settings: Settings,
) -> InferenceAdapter:
    if modality not in MODALITIES:
        raise ValueError(f"unsupported modality: {modality}")

    plan = MODE_PLAN.get(settings.inference_mode)

    if plan is None:
        raise RuntimeError(
            f"unsupported inference mode: {settings.inference_mode}"
        )

    stages = plan[modality]

    if not stages:
        return StubAdapter(modality)

    quality_adapter = (
        _QUALITY_BUILDERS[modality](settings)
        if "quality" in stages
        else StubQualityAdapter()
    )
    defect_adapter = (
        _DEFECT_BUILDERS[modality](settings)
        if "defect" in stages
        else StubDefectAdapter(modality)
    )

    return InferencePipeline(
        quality_adapter=quality_adapter,
        defect_adapter=defect_adapter,
    )
