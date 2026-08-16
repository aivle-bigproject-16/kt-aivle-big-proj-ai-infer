from app.adapters.base import InferencePipeline


class FixedQualityAdapter:
    def __init__(self, label: str, confidence: float):
        self.label = label
        self.confidence = confidence

    def predict_quality(self, image_bytes: bytes) -> dict:
        return {
            "label": self.label,
            "confidence": self.confidence,
        }


class RecordingDefectAdapter:
    def __init__(self):
        self.called = False

    def predict_defects(self, image_bytes: bytes) -> dict:
        self.called = True
        return {
            "label": "REJECT",
            "confidence": 0.9,
            "defects": [],
        }


def test_fail_skips_defect_inference():
    defect = RecordingDefectAdapter()
    pipeline = InferencePipeline(
        quality_adapter=FixedQualityAdapter("FAIL", 0.8),
        defect_adapter=defect,
    )

    result = pipeline.predict(b"image")

    assert result == {
        "label": "FAIL",
        "confidence": 0.8,
        "defects": [],
        "quality": {
            "label": "FAIL",
            "confidence": 0.8,
            "gateMode": "enforce",
        },
    }
    assert defect.called is False


def test_pass_runs_defect_inference():
    defect = RecordingDefectAdapter()
    pipeline = InferencePipeline(
        quality_adapter=FixedQualityAdapter("PASS", 1.0),
        defect_adapter=defect,
    )

    result = pipeline.predict(b"image")

    assert result["label"] == "REJECT"
    assert defect.called is True


def test_pipeline_reports_quality_and_defect_stage_timings():
    defect = RecordingDefectAdapter()
    pipeline = InferencePipeline(
        quality_adapter=FixedQualityAdapter("PASS", 1.0),
        defect_adapter=defect,
    )

    result, timings = pipeline.predict_with_timings(b"image")

    assert result["label"] == "REJECT"
    assert set(timings) == {"quality_ms", "defect_ms", "pipeline_ms"}
    assert all(value >= 0 for value in timings.values())


def test_fail_timing_omits_skipped_defect_stage():
    pipeline = InferencePipeline(
        quality_adapter=FixedQualityAdapter("FAIL", 0.8),
        defect_adapter=RecordingDefectAdapter(),
    )

    _, timings = pipeline.predict_with_timings(b"image")

    assert set(timings) == {"quality_ms", "pipeline_ms"}


def test_shadow_quality_fail_runs_defect_and_keeps_observation():
    defect = RecordingDefectAdapter()
    pipeline = InferencePipeline(
        quality_adapter=FixedQualityAdapter("FAIL", 0.8),
        defect_adapter=defect,
        quality_gate_mode="shadow",
    )

    result = pipeline.predict(b"image")

    assert result["label"] == "REJECT"
    assert result["quality"] == {
        "label": "FAIL",
        "confidence": 0.8,
        "gateMode": "shadow",
    }
    assert defect.called is True
