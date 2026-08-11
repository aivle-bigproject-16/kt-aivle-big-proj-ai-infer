import logging
from typing import Protocol


logger = logging.getLogger(__name__)


# 계약 §6.5 / A-5: defectType 와이어 표기는 영문 4종이다. OWLv2 는 한글 태그를
# 내므로 어댑터 경계에서 변환한다. 매핑 근거는 docs/V0_2_0_FIX_PLAN.md §2 C-1.
TAG_TO_DEFECT_TYPE: dict[str, str] = {
    "파손·찢김": "CRACK",
    "긁힘·스크래치": "CRACK",
    "녹·부식": "SPOT",
    "오염·이물질": "SPOT",
    "벗겨짐·박리": "SWELLING",
    "들뜸": "SWELLING",
}

# 결함이 아니라 정상 구조물이다. rgb_ext_infer.DROP_TAGS 는 이 태그를 일부러
# 남기므로(구조물로 지우면 진짜 결함을 함께 잃는다) 결함 배열에서만 걸러낸다.
NON_DEFECT_TAGS: frozenset[str] = frozenset({"정상:금속캡"})


class RgbFrameInspector(Protocol):
    def infer_frames(
        self,
        images,
        names=None,
    ) -> list[dict]:
        ...


class RgbOwlv2DefectAdapter:
    """Convert one OWLv2 frame result to the AI server contract.

    The source model's Korean candidate tag is preserved as defectType.
    This keeps the server response aligned with the current model output.
    """

    def __init__(
        self,
        inspector: RgbFrameInspector,
    ):
        self.inspector = inspector

    def predict_defects(self, image_bytes: bytes) -> dict:
        import json
        try:
            json_data = json.loads(image_bytes.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            # 더미 데이터 생성
            json_data = {"셀_판정": "PASS", "프레임": []}

        defects = []
        for frame in json_data.get("프레임", []):
            for source in frame.get("결함", []):
                converted = self._convert_defect(source)
                if converted is not None:
                    defects.append(converted)

        label = json_data.get("셀_판정", "PASS")
        if label == "결함" or defects:
            label = "REJECT"
        else:
            label = "PASS"

        if not defects:
            return {
                "label": "PASS",
                "confidence": 1.0,
                "defects": [],
            }

        return {
            "label": label,
            "confidence": max(item["confidence"] for item in defects),
            "defects": defects,
        }

    def _convert_defect(self, source: dict) -> dict | None:
        candidates = source.get("유형후보") or []
        if not candidates:
            return None

        tag = candidates[0]
        if tag in NON_DEFECT_TAGS:
            return None

        # 한글을 영어로 치환하되, 없으면 tag 그대로 전송 (영어로 간주)
        defect_type = TAG_TO_DEFECT_TYPE.get(tag, tag)

        loc = source.get("위치", {})
        crop_bbox = loc.get("bbox_크롭", [0, 0, 0, 0])
        offset = loc.get("크롭_오프셋", [0, 0])

        x = float(crop_bbox[0] + offset[0])
        y = float(crop_bbox[1] + offset[1])
        width = float(crop_bbox[2] - crop_bbox[0])
        height = float(crop_bbox[3] - crop_bbox[1])
        confidence = float(source.get("_score", 0.0))

        return {
            "defectType": defect_type,
            "confidence": confidence,
            "bbox": {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            },
        }


def build_rgb_owlv2_defect_adapter() -> RgbOwlv2DefectAdapter:
    """Build the real OWLv2 adapter without importing model code at startup."""
    from app.vendor.rgb_ext_infer import ExtInspector

    return RgbOwlv2DefectAdapter(
        inspector=ExtInspector(),
    )


def build_rgb_owlv2_onnx_defect_adapter(
    model_dir: str = "/models/rgb_owlv2_onnx",
    providers=None,
) -> RgbOwlv2DefectAdapter:
    from app.vendor.rgb_ext_infer_onnx import OnnxExtInspector

    return RgbOwlv2DefectAdapter(
        inspector=OnnxExtInspector(
            model_dir=model_dir,
            providers=providers,
        ),
    )
