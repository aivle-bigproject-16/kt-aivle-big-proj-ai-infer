from adapters import (
    InferenceAdapter,
    InferencePipeline,
    StubAdapter,
    StubDefectAdapter,
)
from onnx_quality_ct import OnnxCtQualityAdapter
from onnx_quality_rgb import OnnxRgbQualityAdapter
from rgb_owlv2_defect import build_rgb_owlv2_onnx_defect_adapter
from settings import Settings


def build_adapter(
    modality: str,
    settings: Settings,
) -> InferenceAdapter:
    if modality not in {"ct", "rgb"}:
        raise ValueError(f"unsupported modality: {modality}")

    if settings.inference_mode == "stub":
        return StubAdapter(modality)

    if settings.inference_mode in {
        "ct-quality-onnx",
        "quality-onnx",
        "rgb-onnx",
    }:
        if settings.inference_mode == "rgb-onnx":
            if modality == "ct":
                return StubAdapter("ct")

            return InferencePipeline(
                quality_adapter=OnnxRgbQualityAdapter(
                    settings.rgb_quality_model_path
                ),
                defect_adapter=build_rgb_owlv2_onnx_defect_adapter(
                    settings.rgb_defect_model_dir
                ),
            )

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

    raise RuntimeError(
        "INFERENCE_MODE=onnx was requested, but all ONNX "
        "adapters have not been connected yet"
    )
