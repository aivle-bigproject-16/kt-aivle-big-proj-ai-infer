from app.adapters.base import InferencePipeline, StubAdapter
from app.adapters.factory import build_adapter
from app.settings import Settings


def unified_settings() -> Settings:
    return Settings(
        inference_mode="onnx",
        onnx_device="cpu",
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
        "app.adapters.factory.OnnxCtQualityAdapter",
        lambda path, **kwargs: ct_quality,
    )
    monkeypatch.setattr(
        "app.adapters.factory.OnnxCtDefectAdapter",
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
        "app.adapters.factory.OnnxRgbQualityAdapter",
        lambda path, **kwargs: rgb_quality,
    )
    monkeypatch.setattr(
        "app.adapters.rgb_defect_owlv2.build_rgb_owlv2_onnx_defect_adapter",
        lambda path, **kwargs: rgb_defect,
    )

    adapter = build_adapter("rgb", unified_settings())

    assert isinstance(adapter, InferencePipeline)
    assert adapter.quality_adapter is rgb_quality
    assert adapter.defect_adapter is rgb_defect


def test_cuda_mode_is_passed_to_all_onnx_adapters(monkeypatch):
    settings = unified_settings()
    settings = Settings(
        **{
            **settings.__dict__,
            "onnx_device": "cuda",
        }
    )
    calls = {}

    def ct_quality(path, **kwargs):
        calls["ct_quality"] = kwargs
        return object()

    def ct_defect(path, **kwargs):
        calls["ct_defect"] = kwargs
        return object()

    def rgb_quality(path, **kwargs):
        calls["rgb_quality"] = kwargs
        return object()

    def rgb_defect(path, **kwargs):
        calls["rgb_defect"] = kwargs
        return object()

    monkeypatch.setattr(
        "app.adapters.factory.OnnxCtQualityAdapter",
        ct_quality,
    )
    monkeypatch.setattr(
        "app.adapters.factory.OnnxCtDefectAdapter",
        ct_defect,
    )
    monkeypatch.setattr(
        "app.adapters.factory.OnnxRgbQualityAdapter",
        rgb_quality,
    )
    monkeypatch.setattr(
        "app.adapters.rgb_defect_owlv2.build_rgb_owlv2_onnx_defect_adapter",
        rgb_defect,
    )

    build_adapter("ct", settings)
    build_adapter("rgb", settings)

    assert calls["ct_quality"]["providers"][0] == (
        "CUDAExecutionProvider"
    )
    assert calls["ct_defect"]["device"] == "cuda:0"
    assert calls["rgb_quality"]["providers"][0] == (
        "CUDAExecutionProvider"
    )
    assert calls["rgb_defect"]["providers"][0] == (
        "CUDAExecutionProvider"
    )


def test_quality_only_modes_still_receive_the_cuda_provider(monkeypatch):
    settings = Settings(
        **{
            **unified_settings().__dict__,
            "inference_mode": "quality-onnx",
            "onnx_device": "cuda",
        }
    )
    calls = {}

    def record(name):
        def build(path, **kwargs):
            calls[name] = kwargs
            return object()

        return build

    monkeypatch.setattr(
        "app.adapters.factory.OnnxCtQualityAdapter",
        record("ct_quality"),
    )
    monkeypatch.setattr(
        "app.adapters.factory.OnnxRgbQualityAdapter",
        record("rgb_quality"),
    )

    ct_adapter = build_adapter("ct", settings)
    rgb_adapter = build_adapter("rgb", settings)

    assert calls["ct_quality"]["providers"][0] == (
        "CUDAExecutionProvider"
    )
    assert calls["rgb_quality"]["providers"][0] == (
        "CUDAExecutionProvider"
    )
    assert isinstance(ct_adapter, InferencePipeline)
    assert isinstance(rgb_adapter, InferencePipeline)


def test_rgb_only_mode_keeps_ct_on_the_stub():
    settings = Settings(
        **{
            **unified_settings().__dict__,
            "inference_mode": "rgb-onnx",
        }
    )

    assert isinstance(build_adapter("ct", settings), StubAdapter)


def test_configured_thresholds_reach_the_onnx_adapters(monkeypatch):
    settings = Settings(
        **{
            **unified_settings().__dict__,
            "ct_defect_conf_threshold": 0.4,
            "ct_quality_threshold": -0.2,
            "rgb_quality_fail_threshold": 0.7,
        }
    )
    calls = {}

    def record(name):
        def build(path, **kwargs):
            calls[name] = kwargs
            return object()

        return build

    monkeypatch.setattr(
        "app.adapters.factory.OnnxCtQualityAdapter",
        record("ct_quality"),
    )
    monkeypatch.setattr(
        "app.adapters.factory.OnnxCtDefectAdapter",
        record("ct_defect"),
    )
    monkeypatch.setattr(
        "app.adapters.factory.OnnxRgbQualityAdapter",
        record("rgb_quality"),
    )
    monkeypatch.setattr(
        "app.adapters.rgb_defect_owlv2.build_rgb_owlv2_onnx_defect_adapter",
        record("rgb_defect"),
    )

    build_adapter("ct", settings)
    build_adapter("rgb", settings)

    assert calls["ct_defect"]["conf_threshold"] == 0.4
    assert calls["ct_quality"]["threshold"] == -0.2
    assert calls["rgb_quality"]["fail_threshold"] == 0.7
