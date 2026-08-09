from adapters import (
    InferenceAdapter,
    InferencePipeline,
    StubAdapter,
    StubDefectAdapter,
)
from onnx_quality_ct import OnnxCtQualityAdapter
from onnx_quality_rgb import OnnxRgbQualityAdapter
from ct_defect_onnx import OnnxCtDefectAdapter
from settings import Settings


def _build_ct_onnx_pipeline(
    settings: Settings,
) -> InferencePipeline:
    return InferencePipeline(
        quality_adapter=OnnxCtQualityAdapter(
            settings.ct_quality_model_path
        ),
        defect_adapter=OnnxCtDefectAdapter(
            settings.ct_defect_model_path,
            postprocess_type=settings.ct_postprocess_type,
            postprocess_match_metric=(
                settings.ct_postprocess_match_metric
            ),
            postprocess_match_threshold=(
                settings.ct_postprocess_match_threshold
            ),
        ),
    )


def _build_rgb_onnx_pipeline(
    settings: Settings,
) -> InferencePipeline:
    from rgb_owlv2_defect import (
        build_rgb_owlv2_onnx_defect_adapter,
    )

    return InferencePipeline(
        quality_adapter=OnnxRgbQualityAdapter(
            settings.rgb_quality_model_path
        ),
        defect_adapter=build_rgb_owlv2_onnx_defect_adapter(
            settings.rgb_defect_model_dir
        ),
    )


def build_adapter(
    modality: str,
    settings: Settings,
) -> InferenceAdapter:
    if modality not in {"ct", "rgb"}:
        raise ValueError(f"unsupported modality: {modality}")

    if settings.inference_mode == "stub":
        return StubAdapter(modality)

    if settings.inference_mode in {"ct-onnx", "onnx"}:
        if modality == "ct":
            return _build_ct_onnx_pipeline(settings)
        if settings.inference_mode == "ct-onnx":
            return StubAdapter("rgb")

    if settings.inference_mode in {"rgb-onnx", "onnx"}:
        if modality == "rgb":
            return _build_rgb_onnx_pipeline(settings)
        if settings.inference_mode == "rgb-onnx":
            return StubAdapter("ct")

    if settings.inference_mode in {
        "ct-quality-onnx",
        "quality-onnx",
        "rgb-onnx",
    }:
        if modality == "ct":
            quality_adapter = OnnxCtQualityAdapter(
                settings.ct_quality_model_path
            )
        elif settings.inference_mode == "quality-onnx":
            quality_adapter = OnnxRgbQualityAdapter(
                settings.rgb_quality_model_path
            )
        else:
            return StubAdapter("rgb")

        return InferencePipeline(
            quality_adapter=quality_adapter,
            defect_adapter=StubDefectAdapter(modality),
        )

    raise RuntimeError(f"unsupported inference mode: {settings.inference_mode}")
