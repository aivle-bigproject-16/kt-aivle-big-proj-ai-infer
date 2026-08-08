import io

from PIL import Image

from ct_defect_onnx import OnnxCtDefectAdapter


class FakeScore:
    value = 0.81


class FakeCategory:
    name = "porosity"


class FakeBbox:
    minx = 10.0
    miny = 20.0
    maxx = 40.0
    maxy = 70.0


class FakeObjectPrediction:
    score = FakeScore()
    category = FakeCategory()
    bbox = FakeBbox()


class FakePrediction:
    object_prediction_list = [FakeObjectPrediction()]


def png_bytes() -> bytes:
    stream = io.BytesIO()
    Image.new("L", (32, 64), 128).save(stream, format="PNG")
    return stream.getvalue()


def test_ct_adapter_uses_configured_ios_postprocessing():
    calls = []

    def predictor(**kwargs):
        calls.append(kwargs)
        return FakePrediction()

    adapter = OnnxCtDefectAdapter(
        "unused.onnx",
        detection_model=object(),
        predictor=predictor,
        postprocess_type="NMS",
        postprocess_match_metric="IOS",
        postprocess_match_threshold=0.44,
    )

    result = adapter.predict_defects(png_bytes())

    assert result == {
        "label": "REJECT",
        "confidence": 0.81,
        "defects": [
            {
                "defectType": "MICRO_DEFECT",
                "confidence": 0.81,
                "bbox": {
                    "x": 10.0,
                    "y": 20.0,
                    "width": 30.0,
                    "height": 50.0,
                },
            }
        ],
    }
    assert calls[0]["postprocess_type"] == "NMS"
    assert calls[0]["postprocess_match_metric"] == "IOS"
    assert calls[0]["postprocess_match_threshold"] == 0.44
    assert calls[0]["slice_height"] == 1280
    assert calls[0]["slice_width"] == 1280


def test_ct_adapter_returns_pass_for_no_detections():
    class EmptyPrediction:
        object_prediction_list = []

    adapter = OnnxCtDefectAdapter(
        "unused.onnx",
        detection_model=object(),
        predictor=lambda **kwargs: EmptyPrediction(),
    )

    assert adapter.predict_defects(png_bytes()) == {
        "label": "PASS",
        "confidence": 1.0,
        "defects": [],
    }
