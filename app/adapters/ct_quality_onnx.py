import io
import math
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, UnidentifiedImageError


CANVAS = (288, 512)  # (W, H)
PAD = 114
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)
DEFAULT_THRESHOLD = -0.6227158308029175


def preprocess_ct_quality(image_bytes: bytes) -> np.ndarray:
    if not image_bytes:
        raise ValueError("image_bytes must not be empty")

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("L")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("invalid CT image") from exc

    width, height = image.size
    canvas_width, canvas_height = CANVAS
    scale = min(canvas_width / width, canvas_height / height)
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    image = image.resize(
        (resized_width, resized_height),
        Image.Resampling.BILINEAR,
    )
    canvas = Image.new("L", CANVAS, PAD)
    canvas.paste(
        image,
        (
            (canvas_width - resized_width) // 2,
            (canvas_height - resized_height) // 2,
        ),
    )

    rgb = np.asarray(canvas.convert("RGB"), dtype=np.float32)
    tensor = np.transpose(rgb, (2, 0, 1))[None, ...] / 255.0
    return ((tensor - MEAN) / STD).astype(np.float32)


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


class OnnxCtQualityAdapter:
    def __init__(
        self,
        model_path: str | Path,
        threshold: float = DEFAULT_THRESHOLD,
        providers: list[str] | None = None,
        session=None,
    ):
        self.model_path = Path(model_path)
        self.threshold = threshold
        self.session = session or ort.InferenceSession(
            str(self.model_path),
            providers=providers or ["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def predict_quality(self, image_bytes: bytes) -> dict:
        tensor = preprocess_ct_quality(image_bytes)
        output = self.session.run(
            [self.output_name],
            {self.input_name: tensor},
        )[0]
        logit = float(np.asarray(output).reshape(-1)[0])
        fail_probability = sigmoid(logit)

        if logit >= self.threshold:
            return {
                "label": "FAIL",
                "confidence": round(fail_probability, 6),
            }

        return {
            "label": "PASS",
            "confidence": round(1.0 - fail_probability, 6),
        }
