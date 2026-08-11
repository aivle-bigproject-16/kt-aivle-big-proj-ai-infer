import io

import numpy as np
from PIL import Image

from app.adapters.ct_quality_onnx import OnnxCtQualityAdapter, preprocess_ct_quality


class FakeIo:
    def __init__(self, name):
        self.name = name


class FakeSession:
    def __init__(self, logit):
        self.logit = logit
        self.received = None

    def get_inputs(self):
        return [FakeIo("images")]

    def get_outputs(self):
        return [FakeIo("logits")]

    def run(self, output_names, feed):
        self.received = feed["images"]
        return [np.array([[self.logit]], dtype=np.float32)]


def image_bytes(width=100, height=200):
    image = Image.new("L", (width, height), 128)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_preprocess_shape_and_dtype():
    tensor = preprocess_ct_quality(image_bytes())

    assert tensor.shape == (1, 3, 512, 288)
    assert tensor.dtype == np.float32


def test_fail_when_logit_reaches_threshold():
    session = FakeSession(logit=0.0)
    adapter = OnnxCtQualityAdapter("unused.onnx", session=session)

    result = adapter.predict_quality(image_bytes())

    assert result["label"] == "FAIL"
    assert session.received.shape == (1, 3, 512, 288)


def test_pass_when_logit_is_below_threshold():
    session = FakeSession(logit=-10.0)
    adapter = OnnxCtQualityAdapter("unused.onnx", session=session)

    result = adapter.predict_quality(image_bytes())

    assert result["label"] == "PASS"
    assert result["confidence"] > 0.99
