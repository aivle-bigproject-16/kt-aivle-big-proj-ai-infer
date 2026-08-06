from adapters import InferencePipeline


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
