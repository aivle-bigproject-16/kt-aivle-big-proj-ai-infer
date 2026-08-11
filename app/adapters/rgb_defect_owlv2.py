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
        if not image_bytes:
            raise ValueError("image_bytes must not be empty")

        frames = self.inspector.infer_frames(
            [image_bytes],
            names=["request.jpg"],
        )

        if len(frames) != 1:
            raise RuntimeError(
                "RGB inspector must return exactly one frame result"
            )

        frame = frames[0]

        if frame.get("판정") == "정상":
            return self._pass_result(frame)

        defects = []

        for source in frame.get("결함", []):
            converted = self._convert_defect(source)

            if converted is not None:
                defects.append(converted)

        if not defects:
            # 결함 근거가 하나도 남지 않은 REJECT 는 BE 계약(REJECT = 결함 N행)을
            # 만족시키지 못한다. 정상 구조물 태그만 검출된 경우이므로 PASS 로 낸다.
            logger.warning(
                "RGB frame flagged as defective but no contract defect "
                "survived tag mapping; reporting PASS"
            )
            return self._pass_result(frame)

        return {
            "label": "REJECT",
            "confidence": max(
                item["confidence"] for item in defects
            ),
            "defects": defects,
        }

    @staticmethod
    def _pass_result(frame: dict) -> dict:
        """A-4: PASS 의 최상위 confidence = 1 - (임계값 미만 최고 결함 점수)."""
        max_score = float(frame.get("_max_score") or 0.0)
        confidence = min(max(1.0 - max_score, 0.0), 1.0)

        return {
            "label": "PASS",
            "confidence": round(confidence, 6),
            "defects": [],
        }

    def _convert_defect(self, source: dict) -> dict | None:
        """계약 결함 1건으로 변환한다. 결함이 아닌 태그는 None 을 준다."""
        candidates = source.get("유형후보") or []

        if not candidates:
            raise ValueError(
                "RGB defect has no source type candidate"
            )

        tag = candidates[0]

        if tag in NON_DEFECT_TAGS:
            return None

        defect_type = TAG_TO_DEFECT_TYPE.get(tag)

        if defect_type is None:
            # 계약에 없는 값을 내보내느니 결함 하나를 버린다. 요청 전체를
            # 실패시키지 않는다.
            logger.warning("dropping unmapped RGB defect tag: %s", tag)
            return None

        x1, y1, x2, y2 = source["위치"]["bbox"]
        confidence = float(source["_score"])

        return {
            "defectType": defect_type,
            "confidence": confidence,
            "bbox": {
                "x": float(x1),
                "y": float(y1),
                "width": float(x2 - x1),
                "height": float(y2 - y1),
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
