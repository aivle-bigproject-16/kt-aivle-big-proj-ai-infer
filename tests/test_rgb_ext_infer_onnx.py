from pathlib import Path

import numpy as np
import pytest

from app.vendor.rgb_ext_infer_onnx import (
    build_session_feed,
    postprocess_owlv2,
    resolve_onnx_model,
)


def test_session_feed_contains_only_declared_onnx_inputs():
    encoded = {
        "input_ids": [[1, 2]],
        "attention_mask": [[1, 1]],
        "pixel_values": [[[[0.0]]]],
        "token_type_ids": [[0, 0]],
    }

    feed = build_session_feed(
        encoded,
        {"input_ids", "attention_mask", "pixel_values"},
    )

    assert set(feed) == {
        "input_ids",
        "attention_mask",
        "pixel_values",
    }
    assert "token_type_ids" not in feed


def test_session_feed_rejects_a_missing_required_input():
    with pytest.raises(ValueError, match="attention_mask"):
        build_session_feed(
            {"input_ids": [[1, 2]]},
            {"input_ids", "attention_mask"},
        )


def test_resolve_onnx_model_accepts_one_model(tmp_path: Path):
    model = tmp_path / "model.onnx"
    model.write_bytes(b"onnx")

    assert resolve_onnx_model(tmp_path) == model


def test_resolve_onnx_model_rejects_ambiguous_models(tmp_path: Path):
    (tmp_path / "a.onnx").write_bytes(b"a")
    (tmp_path / "b.onnx").write_bytes(b"b")

    with pytest.raises(RuntimeError, match="exactly one"):
        resolve_onnx_model(tmp_path)


def test_postprocess_owlv2_scales_center_boxes_to_image_coordinates():
    logits = np.array([[[0.0, 2.0], [-10.0, -10.0]]], dtype=np.float32)
    pred_boxes = np.array(
        [[[0.5, 0.5, 0.4, 0.2], [0.5, 0.5, 0.2, 0.2]]],
        dtype=np.float32,
    )

    results = postprocess_owlv2(
        logits=logits,
        pred_boxes=pred_boxes,
        target_sizes=[[100, 200]],
        threshold=0.6,
    )

    assert results[0]["labels"].tolist() == [1]
    assert results[0]["scores"].tolist() == pytest.approx([0.880797])
    np.testing.assert_allclose(
        results[0]["boxes"],
        np.array([[60.0, 40.0, 140.0, 60.0]]),
        atol=1e-5,
    )
