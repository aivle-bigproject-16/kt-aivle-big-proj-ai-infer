import pytest

from rgb_owlv2_defect import (
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


def test_model_defect_types_are_returned_without_mapping():
    model_types = [
        "녹·부식",
        "벗겨짐·박리",
        "파손·찢김",
        "긁힘·스크래치",
        "들뜸",
        "오염·이물질",
    ]
    inspector = FixedInspector(
        {
            "판정": "결함",
            "결함": [
                {
                    "유형후보": [model_type],
                    "_score": 0.81 - index * 0.01,
                    "위치": {
                        "bbox": [
                            10 + index,
                            20 + index,
                            40 + index,
                            70 + index,
                        ]
                    },
                }
                for index, model_type in enumerate(model_types)
            ],
        }
    )
    adapter = RgbOwlv2DefectAdapter(inspector=inspector)

    result = adapter.predict_defects(b"jpeg")

    assert result["label"] == "REJECT"
    assert result["confidence"] == 0.81
    assert [
        defect["defectType"]
        for defect in result["defects"]
    ] == model_types
    assert result["defects"][0]["bbox"] == {
        "x": 10.0,
        "y": 20.0,
        "width": 30.0,
        "height": 50.0,
    }


def test_empty_image_is_rejected_before_model_call():
    inspector = FixedInspector({"판정": "정상", "결함": []})
    adapter = RgbOwlv2DefectAdapter(inspector=inspector)

    with pytest.raises(ValueError, match="image_bytes"):
        adapter.predict_defects(b"")

    assert inspector.calls == []


def test_defect_without_a_type_candidate_is_rejected():
    inspector = FixedInspector(
        {
            "판정": "결함",
            "결함": [
                {
                    "유형후보": [],
                    "_score": 0.81,
                    "위치": {"bbox": [10, 20, 40, 70]},
                }
            ],
        }
    )
    adapter = RgbOwlv2DefectAdapter(inspector=inspector)

    with pytest.raises(ValueError, match="source type candidate"):
        adapter.predict_defects(b"jpeg")
