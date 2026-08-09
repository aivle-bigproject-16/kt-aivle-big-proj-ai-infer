import io
from collections.abc import Callable
from typing import Any

from PIL import Image


class OnnxCtDefectAdapter:
    """Run the CT segmentation ONNX model through SAHI."""

    def __init__(
        self,
        model_path: str,
        *,
        postprocess_type: str = "NMS",
        postprocess_match_metric: str = "IOS",
        postprocess_match_threshold: float = 0.44,
        device: str = "cpu",
        detection_model: Any | None = None,
        predictor: Callable[..., Any] | None = None,
    ):
        self.postprocess_type = postprocess_type
        self.postprocess_match_metric = postprocess_match_metric
        self.postprocess_match_threshold = (
            postprocess_match_threshold
        )

        if detection_model is None or predictor is None:
            from sahi import AutoDetectionModel
            from sahi.predict import get_sliced_prediction

            if detection_model is None:
                detection_model = AutoDetectionModel.from_pretrained(
                    model_type="ultralytics",
                    model_path=model_path,
                    task="segment",
                    image_size=1280,
                    confidence_threshold=0.05,
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
            return {
                "label": "PASS",
                "confidence": 1.0,
                "defects": [],
            }

        return {
            "label": "REJECT",
            "confidence": max(
                defect["confidence"] for defect in defects
            ),
            "defects": defects,
        }
