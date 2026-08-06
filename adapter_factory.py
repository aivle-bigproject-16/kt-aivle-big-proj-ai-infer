from adapters import InferenceAdapter, StubAdapter
from settings import Settings


def build_adapter(
    modality: str,
    settings: Settings,
) -> InferenceAdapter:
    if modality not in {"ct", "rgb"}:
        raise ValueError(f"unsupported modality: {modality}")

    if settings.inference_mode == "stub":
        return StubAdapter(modality)

    raise RuntimeError(
        "INFERENCE_MODE=onnx was requested, but ONNX adapters "
        "have not been connected yet"
    )
