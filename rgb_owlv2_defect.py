from collections.abc import Callable
from typing import Protocol


SERVER_DEFECT_TYPES = {"CRACK", "SPOT"}


class RgbFrameInspector(Protocol):
    def infer_frames(
        self,
        images,
        names=None,
    ) -> list[dict]:
        ...


class RgbDefectTypeMappingRequired(RuntimeError):
    """Raised when an OWLv2 tag has no approved server enum mapping."""


class RgbOwlv2DefectAdapter:
    """Convert one OWLv2 frame result to the AI server contract.

    The source model exposes six unverified Korean candidate tags while
    the server contract accepts only CRACK and SPOT. A mapper is therefore
    mandatory for defect responses and intentionally has no default.
    """

    def __init__(
        self,
        inspector: RgbFrameInspector,
        defect_type_mapper: Callable[[str], str] | None = None,
    ):
        self.inspector = inspector
        self.defect_type_mapper = defect_type_mapper

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
            raise RgbDefectTypeMappingRequired(
                "RGB defect has no source type candidate"
            )

        if self.defect_type_mapper is None:
            raise RgbDefectTypeMappingRequired(
                "An approved RGB defect type mapping is required"
            )

        defect_type = self.defect_type_mapper(candidates[0])

        if defect_type not in SERVER_DEFECT_TYPES:
            raise ValueError(
                "RGB defect mapper must return CRACK or SPOT"
            )

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


def build_rgb_owlv2_defect_adapter(
    defect_type_mapper: Callable[[str], str] | None = None,
) -> RgbOwlv2DefectAdapter:
    """Build the real OWLv2 adapter without importing model code at startup."""
    from rgb_ext_infer import ExtInspector

    return RgbOwlv2DefectAdapter(
        inspector=ExtInspector(),
        defect_type_mapper=defect_type_mapper,
    )
