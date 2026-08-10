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


def _defect_frame(tags: list[str]) -> dict:
    return {
        "판정": "결함",
        "결함": [
            {
                "유형후보": [tag],
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
            for index, tag in enumerate(tags)
        ],
    }


def test_model_tags_are_mapped_to_contract_defect_types():
    model_types = [
        "녹·부식",
        "벗겨짐·박리",
        "파손·찢김",
        "긁힘·스크래치",
        "들뜸",
        "오염·이물질",
    ]
    inspector = FixedInspector(_defect_frame(model_types))
    adapter = RgbOwlv2DefectAdapter(inspector=inspector)

    result = adapter.predict_defects(b"jpeg")

    assert result["label"] == "REJECT"
    assert result["confidence"] == 0.81
    assert [
        defect["defectType"]
        for defect in result["defects"]
    ] == [
        "SPOT",
        "SWELLING",
        "CRACK",
        "CRACK",
        "SWELLING",
        "SPOT",
    ]
    assert result["defects"][0]["bbox"] == {
        "x": 10.0,
        "y": 20.0,
        "width": 30.0,
        "height": 50.0,
    }


def test_structural_tag_is_dropped_from_defects():
    inspector = FixedInspector(
        _defect_frame(["정상:금속캡", "파손·찢김"])
    )
    adapter = RgbOwlv2DefectAdapter(inspector=inspector)

    result = adapter.predict_defects(b"jpeg")

    assert result["label"] == "REJECT"
    assert [
        defect["defectType"]
        for defect in result["defects"]
    ] == ["CRACK"]
    assert result["confidence"] == 0.80


def test_unmapped_tag_is_dropped_instead_of_failing_the_request():
    inspector = FixedInspector(
        _defect_frame(["듣도보도못한태그", "들뜸"])
    )
    adapter = RgbOwlv2DefectAdapter(inspector=inspector)

    result = adapter.predict_defects(b"jpeg")

    assert [
        defect["defectType"]
        for defect in result["defects"]
    ] == ["SWELLING"]


def test_defect_frame_without_contract_defects_falls_back_to_pass():
    frame = _defect_frame(["정상:금속캡"])
    frame["_max_score"] = 0.4
    inspector = FixedInspector(frame)
    adapter = RgbOwlv2DefectAdapter(inspector=inspector)

    result = adapter.predict_defects(b"jpeg")

    assert result == {
        "label": "PASS",
        "confidence": 0.6,
        "defects": [],
    }


def test_pass_confidence_follows_a4_rule():
    inspector = FixedInspector(
        {
            "판정": "정상",
            "결함": [],
            "_max_score": 0.09,
        }
    )
    adapter = RgbOwlv2DefectAdapter(inspector=inspector)

    result = adapter.predict_defects(b"jpeg")

    assert result["confidence"] == 0.91


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
