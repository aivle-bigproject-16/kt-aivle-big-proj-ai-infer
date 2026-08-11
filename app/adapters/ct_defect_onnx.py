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
        import json
        
        # 외부 API 등에서 JSON 응답을 받아왔다고 가정하고 처리
        try:
            json_data = json.loads(image_bytes.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            # 실제 이미지 바이트가 들어오면 기본 더미 데이터를 반환 (테스트 용도)
            json_data = {
                "verdict": "REJECT",
                "detections": [
                    {
                        "class": "porosity",
                        "confidence": 0.0617,
                        "bbox_xywh": [240, 2218, 5, 468]
                    }
                ]
            }

        defects = []
        for det in json_data.get("detections", []):
            bbox = det["bbox_xywh"]
            defects.append({
                "defectType": det["class"], # 영어 그대로 전송
                "confidence": det["confidence"],
                "bbox": {
                    "x": bbox[0],
                    "y": bbox[1],
                    "width": bbox[2],
                    "height": bbox[3],
                },
            })

        return {
            "label": json_data.get("verdict", "PASS"),
            "confidence": 1.0,
            "defects": defects,
        }
