import pytest

from rgb_owlv2_defect import (
    RgbDefectTypeMappingRequired,
    RgbOwlv2DefectAdapter,
)


class FixedInspector:
    def __init__(self, frame: dict):
        self.frame = frame
        self.calls = []

    def infer_frames(self, images, names=None):
        self.calls.append((list(images), list(names or [])))
        return [self.frame]


def test_normal_frame_returns_pass():
    inspector = FixedInspector(
        {
            "판정": "정상",
            "결함": [],
        }
    )
    adapter = RgbOwlv2DefectAdapter(inspector=inspector)

    result = adapter.predict_defects(b"jpeg")

    assert result == {
        "label": "PASS",
        "confidence": 1.0,
        "defects": [],
    }
    assert inspector.calls == [([b"jpeg"], ["request.jpg"])]


def test_defect_frame_requires_an_explicit_type_mapping():
    inspector = FixedInspector(
        {
            "판정": "결함",
            "결함": [
                {
                    "유형후보": ["긁힘·스크래치"],
                    "_score": 0.81,
                    "위치": {"bbox": [10, 20, 40, 70]},
                }
            ],
        }
    )
    adapter = RgbOwlv2DefectAdapter(inspector=inspector)

    with pytest.raises(RgbDefectTypeMappingRequired):
        adapter.predict_defects(b"jpeg")


def test_defect_frame_is_converted_to_server_contract():
    inspector = FixedInspector(
        {
            "판정": "결함",
            "결함": [
                {
                    "유형후보": ["긁힘·스크래치"],
                    "_score": 0.81,
                    "위치": {"bbox": [10, 20, 40, 70]},
                },
                {
                    "유형후보": ["오염·이물질"],
                    "_score": 0.73,
                    "위치": {"bbox": [100, 110, 130, 150]},
                },
            ],
        }
    )
    mapping = {
        "긁힘·스크래치": "CRACK",
        "오염·이물질": "SPOT",
    }
    adapter = RgbOwlv2DefectAdapter(
        inspector=inspector,
        defect_type_mapper=mapping.__getitem__,
    )

    result = adapter.predict_defects(b"jpeg")

    assert result == {
        "label": "REJECT",
        "confidence": 0.81,
        "defects": [
            {
                "defectType": "CRACK",
                "confidence": 0.81,
                "bbox": {
                    "x": 10.0,
                    "y": 20.0,
                    "width": 30.0,
                    "height": 50.0,
                },
            },
            {
                "defectType": "SPOT",
                "confidence": 0.73,
                "bbox": {
                    "x": 100.0,
                    "y": 110.0,
                    "width": 30.0,
                    "height": 40.0,
                },
            },
        ],
    }


def test_empty_image_is_rejected_before_model_call():
    inspector = FixedInspector({"판정": "정상", "결함": []})
    adapter = RgbOwlv2DefectAdapter(inspector=inspector)

    with pytest.raises(ValueError, match="image_bytes"):
        adapter.predict_defects(b"")

    assert inspector.calls == []
