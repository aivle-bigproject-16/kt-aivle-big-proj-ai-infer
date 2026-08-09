from adapters import InferencePipeline
from adapter_factory import build_adapter
from settings import Settings


def unified_settings() -> Settings:
    return Settings(
        inference_mode="onnx",
        ct_quality_model_path="ct-quality.onnx",
        ct_defect_model_path="ct-defect.onnx",
        rgb_quality_model_path="rgb-quality.onnx",
        rgb_defect_model_dir="rgb-defect",
        ct_postprocess_type="NMS",
        ct_postprocess_match_metric="IOS",
        ct_postprocess_match_threshold=0.44,
    )


def test_unified_onnx_mode_builds_ct_pipeline(monkeypatch):
    ct_quality = object()
    ct_defect = object()

    monkeypatch.setattr(
        "adapter_factory.OnnxCtQualityAdapter",
        lambda path: ct_quality,
    )
    monkeypatch.setattr(
        "adapter_factory.OnnxCtDefectAdapter",
        lambda *args, **kwargs: ct_defect,
    )

    adapter = build_adapter("ct", unified_settings())

    assert isinstance(adapter, InferencePipeline)
    assert adapter.quality_adapter is ct_quality
    assert adapter.defect_adapter is ct_defect


def test_unified_onnx_mode_builds_rgb_pipeline(monkeypatch):
    rgb_quality = object()
    rgb_defect = object()

    monkeypatch.setattr(
        "adapter_factory.OnnxRgbQualityAdapter",
        lambda path: rgb_quality,
    )
    monkeypatch.setattr(
        "rgb_owlv2_defect.build_rgb_owlv2_onnx_defect_adapter",
        lambda path: rgb_defect,
    )

    adapter = build_adapter("rgb", unified_settings())

    assert isinstance(adapter, InferencePipeline)
    assert adapter.quality_adapter is rgb_quality
    assert adapter.defect_adapter is rgb_defect
