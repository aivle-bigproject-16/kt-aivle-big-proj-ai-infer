from PIL import Image

from app.vendor.rgb_ext_infer import ExtInspector


def _images():
    image = Image.new("RGB", (100, 200), (10, 10, 10))
    return image, image


def _boxes(count: int, score: float, tag: str = "긁힘·스크래치"):
    return [
        (10.0, 20.0, 40.0, 70.0, score, tag)
        for _ in range(count)
    ]


def _frame(boxes):
    inspector = ExtInspector()
    orig, crop = _images()

    return inspector._frame_result(
        "frame_0",
        orig,
        crop,
        (0, 0),
        True,
        boxes,
    )


def test_max_score_is_reported_for_a_normal_frame():
    frame = _frame(_boxes(3, 0.09))

    assert frame["판정"] == "정상"
    assert frame["_max_score"] == 0.09


def test_max_score_is_zero_without_any_box():
    frame = _frame([])

    assert frame["_max_score"] == 0.0


def test_gate_without_localisable_box_promotes_the_top_gate_box():
    boxes = _boxes(7, 0.11) + [(1.0, 2.0, 30.0, 60.0, 0.115, "들뜸")]
    boxes.sort(key=lambda item: -item[4])

    frame = _frame(boxes)

    assert frame["판정"] == "결함"
    assert len(frame["결함"]) == 1
    assert frame["결함"][0]["_score"] == 0.115
    assert frame["결함"][0]["유형후보"] == ["들뜸"]


def test_localisable_boxes_are_used_as_before():
    boxes = _boxes(7, 0.11) + [(1.0, 2.0, 30.0, 60.0, 0.5, "들뜸")]
    boxes.sort(key=lambda item: -item[4])

    frame = _frame(boxes)

    assert frame["판정"] == "결함"
    assert [defect["_score"] for defect in frame["결함"]] == [0.5]
