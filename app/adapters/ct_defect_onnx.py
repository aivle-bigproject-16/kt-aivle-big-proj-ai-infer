import io
from collections.abc import Callable
from typing import Any

from PIL import Image


# SAHI 가 박스를 회수하는 하한. 이 아래는 애초에 후보로도 안 잡힌다.
RETRIEVAL_THRESHOLD = 0.05

# 결함으로 채택할 점수. RETRIEVAL_THRESHOLD 와 같으면 후보 = 채택이라
# 계약 A-4 의 "임계값 미만 최고 점수"가 늘 비고 PASS 신뢰도는 1.0 이 된다.
DEFAULT_CONF_THRESHOLD = 0.05


class OnnxCtDefectAdapter:
    """Run the CT segmentation ONNX model through SAHI."""

    def __init__(
        self,
        model_path: str,
        *,
        postprocess_type: str = "NMS",
        postprocess_match_metric: str = "IOS",
        postprocess_match_threshold: float = 0.44,
        conf_threshold: float = DEFAULT_CONF_THRESHOLD,
        device: str = "cpu",
        detection_model: Any | None = None,
        predictor: Callable[..., Any] | None = None,
    ):
        self.postprocess_type = postprocess_type
        self.postprocess_match_metric = postprocess_match_metric
        self.postprocess_match_threshold = (
            postprocess_match_threshold
        )
        self.conf_threshold = conf_threshold

        if detection_model is None or predictor is None:
            from sahi import AutoDetectionModel
            from sahi.predict import get_sliced_prediction

            if detection_model is None:
                detection_model = AutoDetectionModel.from_pretrained(
                    model_type="ultralytics",
                    model_path=model_path,
                    task="segment",
                    image_size=1280,
                    confidence_threshold=min(
                        RETRIEVAL_THRESHOLD,
                        conf_threshold,
                    ),
                    device=device,
                    category_mapping={"0": "porosity"},
                )
            if predictor is None:
                predictor = get_sliced_prediction

        self.detection_model = detection_model
        self.predictor = predictor

    def predict_defects(self, image_bytes: bytes) -> dict:
        if not image_bytes:
            raise ValueError("image_bytes must not be empty")

        with Image.open(io.BytesIO(image_bytes)) as source:
            image = source.convert("RGB")
            prediction = self.predictor(
                image=image,
                detection_model=self.detection_model,
                slice_height=1280,
                slice_width=1280,
                overlap_height_ratio=0.2,
                overlap_width_ratio=0.2,
                perform_standard_pred=True,
                postprocess_type=self.postprocess_type,
                postprocess_match_metric=(
                    self.postprocess_match_metric
                ),
                postprocess_match_threshold=(
                    self.postprocess_match_threshold
                ),
                verbose=0,
            )

        defects = []
        rejected_scores = []

        for item in prediction.object_prediction_list:
            if item.category.name != "porosity":
                raise ValueError(
                    "unsupported CT defect class: "
                    f"{item.category.name}"
                )

            minx = float(item.bbox.minx)
            miny = float(item.bbox.miny)
            maxx = float(item.bbox.maxx)
            maxy = float(item.bbox.maxy)
            confidence = float(item.score.value)

            if confidence < self.conf_threshold:
                rejected_scores.append(confidence)
                continue

            defects.append(
                {
                    "defectType": "MICRO_DEFECT",
                    "confidence": confidence,
                    "bbox": {
                        "x": minx,
                        "y": miny,
                        "width": maxx - minx,
                        "height": maxy - miny,
                    },
                }
            )

        if not defects:
            # A-4: PASS 의 최상위 confidence = 1 - (임계값 미만 최고 결함 점수).
            # 후보가 아예 없으면 1.0 이다.
            top_rejected = max(rejected_scores, default=0.0)
            confidence = min(max(1.0 - top_rejected, 0.0), 1.0)

            return {
                "label": "PASS",
                "confidence": round(confidence, 6),
                "defects": [],
            }

        return {
            "label": "REJECT",
            "confidence": max(
                defect["confidence"] for defect in defects
            ),
            "defects": defects,
        }
