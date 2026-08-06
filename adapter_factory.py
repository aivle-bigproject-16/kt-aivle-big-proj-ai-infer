from adapters import (
    InferenceAdapter,
    InferencePipeline,
    StubAdapter,
    StubDefectAdapter,
)
from onnx_quality_ct import OnnxCtQualityAdapter
from settings import Settings


def build_adapter(
    modality: str,
    settings: Settings,
) -> InferenceAdapter:
    if modality not in {"ct", "rgb"}:
        raise ValueError(f"unsupported modality: {modality}")

    if settings.inference_mode == "stub":
        return StubAdapter(modality)

    if settings.inference_mode == "ct-quality-onnx":
        if modality == "ct":
            return InferencePipeline(
                quality_adapter=OnnxCtQualityAdapter(
                    settings.ct_quality_model_path
                ),
                defect_adapter=StubDefectAdapter("ct"),
            )
        return StubAdapter("rgb")

    raise RuntimeError(
        "INFERENCE_MODE=onnx was requested, but all ONNX "
        "adapters have not been connected yet"
    )
