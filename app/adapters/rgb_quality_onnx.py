import io
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, UnidentifiedImageError


SIZE = 320
FAIL_THRESHOLD = 0.3


def preprocess_rgb_quality(image_bytes: bytes) -> np.ndarray:
    if not image_bytes:
        raise ValueError("image_bytes must not be empty")

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("invalid RGB image") from exc

    width, height = image.size
    scale = min(SIZE / width, SIZE / height)
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    image = image.resize(
        (resized_width, resized_height),
        Image.Resampling.BILINEAR,
    )
    canvas = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    canvas.paste(
        image,
        (
            (SIZE - resized_width) // 2,
            (SIZE - resized_height) // 2,
        ),
    )

    # The Keras model contains its own Rescaling(1/127.5, -1) layer.
    return np.asarray(canvas, dtype=np.float32)[None, ...]


class OnnxRgbQualityAdapter:
    def __init__(
        self,
        model_path: str | Path,
        fail_threshold: float = FAIL_THRESHOLD,
        providers: list[str] | None = None,
        session=None,
    ):
        self.model_path = Path(model_path)
        self.fail_threshold = fail_threshold
        self.session = session or ort.InferenceSession(
            str(self.model_path),
            providers=providers or ["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def predict_quality(self, image_bytes: bytes) -> dict:
        tensor = preprocess_rgb_quality(image_bytes)
        output = self.session.run(
            [self.output_name],
            {self.input_name: tensor},
        )[0]
        probabilities = np.asarray(output, dtype=np.float32).reshape(-1)

        if probabilities.size != 2:
            raise RuntimeError(
                f"expected two RGB quality probabilities, got {probabilities.size}"
            )

        # 채널 순서는 학습 때 Keras 가 클래스 디렉터리 이름을 사전순으로 매긴
        # 결과다 — 0 = fail, 1 = pass. 모델을 다시 내보내면 이 가정부터 확인한다.
        fail_probability = float(probabilities[0])
        pass_probability = float(probabilities[1])

        if fail_probability >= self.fail_threshold:
            return {
                "label": "FAIL",
                "confidence": round(fail_probability, 6),
            }

        return {
            "label": "PASS",
            "confidence": round(pass_probability, 6),
        }
