import io

import numpy as np
from PIL import Image

from onnx_quality_rgb import OnnxRgbQualityAdapter, preprocess_rgb_quality


class FakeIo:
    def __init__(self, name):
        self.name = name


class FakeSession:
    def __init__(self, probabilities):
        self.probabilities = probabilities
        self.received = None

    def get_inputs(self):
        return [FakeIo("images")]

    def get_outputs(self):
        return [FakeIo("output_0")]

    def run(self, output_names, feed):
        self.received = feed["images"]
        return [np.array([self.probabilities], dtype=np.float32)]


def image_bytes(width=200, height=100):
    image = Image.new("RGB", (width, height), (255, 128, 0))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_preprocess_shape_dtype_and_black_padding():
    tensor = preprocess_rgb_quality(image_bytes())

    assert tensor.shape == (1, 320, 320, 3)
    assert tensor.dtype == np.float32
    assert np.all(tensor[0, 0, 0] == 0.0)


def test_fail_uses_class_zero_probability():
    session = FakeSession([0.3, 0.7])
    adapter = OnnxRgbQualityAdapter("unused.onnx", session=session)

    result = adapter.predict_quality(image_bytes())

    assert result == {"label": "FAIL", "confidence": 0.3}
    assert session.received.shape == (1, 320, 320, 3)


def test_pass_uses_class_one_probability():
    session = FakeSession([0.2, 0.8])
    adapter = OnnxRgbQualityAdapter("unused.onnx", session=session)

    result = adapter.predict_quality(image_bytes())

    assert result == {"label": "PASS", "confidence": 0.8}
