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


def test_cell_min_valid_coverage_defaults_to_eighty_percent(
    monkeypatch,
):
    monkeypatch.delenv("CELL_MIN_VALID_COVERAGE", raising=False)

    assert load_settings().cell_min_valid_coverage == 0.8


@pytest.mark.parametrize("value", ["0", "1.1", "-0.1"])
def test_invalid_cell_min_valid_coverage_is_rejected(
    monkeypatch,
    value,
):
    monkeypatch.setenv("CELL_MIN_VALID_COVERAGE", value)

    with pytest.raises(ValueError):
        load_settings()


def test_rgb_cell_reject_rate_defaults_to_seventy_percent(monkeypatch):
    monkeypatch.delenv("RGB_CELL_REJECT_RATE_THRESHOLD", raising=False)

    assert load_settings().rgb_cell_reject_rate_threshold == 0.7


@pytest.mark.parametrize("value", ["0", "1.1", "-0.1"])
def test_invalid_rgb_cell_reject_rate_is_rejected(monkeypatch, value):
    monkeypatch.setenv("RGB_CELL_REJECT_RATE_THRESHOLD", value)

    with pytest.raises(ValueError, match="RGB_CELL_REJECT_RATE_THRESHOLD"):
        load_settings()


def test_ct_quality_gate_defaults_to_enforce(monkeypatch):
    monkeypatch.delenv("CT_QUALITY_GATE_MODE", raising=False)

    assert load_settings().ct_quality_gate_mode == "enforce"


def test_ct_quality_gate_accepts_shadow(monkeypatch):
    monkeypatch.setenv("CT_QUALITY_GATE_MODE", "shadow")

    assert load_settings().ct_quality_gate_mode == "shadow"


def test_invalid_ct_quality_gate_is_rejected(monkeypatch):
    monkeypatch.setenv("CT_QUALITY_GATE_MODE", "bypass")

    with pytest.raises(ValueError, match="CT_QUALITY_GATE_MODE"):
        load_settings()
