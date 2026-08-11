import pytest

from app.settings import load_settings


def test_onnx_device_defaults_to_cpu(monkeypatch):
    monkeypatch.delenv("ONNX_DEVICE", raising=False)

    assert load_settings().onnx_device == "cpu"


def test_onnx_device_accepts_cuda(monkeypatch):
    monkeypatch.setenv("ONNX_DEVICE", "cuda")

    assert load_settings().onnx_device == "cuda"


def test_invalid_onnx_device_is_rejected(monkeypatch):
    monkeypatch.setenv("ONNX_DEVICE", "gpu")

    with pytest.raises(ValueError, match="ONNX_DEVICE"):
        load_settings()


def test_ct_postprocess_defaults_to_validated_onnx_candidate(monkeypatch):
    monkeypatch.delenv("CT_POSTPROCESS_TYPE", raising=False)
    monkeypatch.delenv("CT_POSTPROCESS_MATCH_METRIC", raising=False)
    monkeypatch.delenv("CT_POSTPROCESS_MATCH_THRESHOLD", raising=False)

    settings = load_settings()

    assert settings.ct_postprocess_type == "NMS"
    assert settings.ct_postprocess_match_metric == "IOS"
    assert settings.ct_postprocess_match_threshold == 0.44


def test_ct_postprocess_can_be_changed_by_environment(monkeypatch):
    monkeypatch.setenv("CT_POSTPROCESS_TYPE", "NMS")
    monkeypatch.setenv("CT_POSTPROCESS_MATCH_METRIC", "IOU")
    monkeypatch.setenv("CT_POSTPROCESS_MATCH_THRESHOLD", "0.5")

    settings = load_settings()

    assert settings.ct_postprocess_match_metric == "IOU"
    assert settings.ct_postprocess_match_threshold == 0.5


def test_invalid_ct_postprocess_metric_is_rejected(monkeypatch):
    monkeypatch.setenv("CT_POSTPROCESS_MATCH_METRIC", "INVALID")

    with pytest.raises(ValueError, match="CT_POSTPROCESS_MATCH_METRIC"):
        load_settings()
