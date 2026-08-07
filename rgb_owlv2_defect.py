from typing import Protocol


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
            return {
                "label": "PASS",
                "confidence": 1.0,
                "defects": [],
            }

        source_defects = frame.get("결함", [])
        defects = [
            self._convert_defect(source)
            for source in source_defects
        ]

        return {
            "label": "REJECT",
            "confidence": max(
                (item["confidence"] for item in defects),
                default=0.0,
            ),
            "defects": defects,
        }

    def _convert_defect(self, source: dict) -> dict:
        candidates = source.get("유형후보") or []

        if not candidates:
            raise ValueError(
                "RGB defect has no source type candidate"
            )

        defect_type = candidates[0]

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
    from rgb_ext_infer import ExtInspector

    return RgbOwlv2DefectAdapter(
        inspector=ExtInspector(),
    )
