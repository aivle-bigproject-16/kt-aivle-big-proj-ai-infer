import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

import main
from rgb_owlv2_defect import TAG_TO_DEFECT_TYPE
from schemas import DefectType


client = TestClient(main.app)


def test_response_schema_accepts_only_the_four_contract_codes():
    adapter = TypeAdapter(DefectType)
    contract_codes = ["SWELLING", "SPOT", "MICRO_DEFECT", "CRACK"]

    assert [
        adapter.validate_python(value) for value in contract_codes
    ] == contract_codes


def test_response_schema_rejects_raw_model_labels():
    adapter = TypeAdapter(DefectType)

    with pytest.raises(ValidationError):
        adapter.validate_python("녹·부식")


def test_every_rgb_tag_maps_into_the_contract_codes():
    adapter = TypeAdapter(DefectType)

    for defect_type in TAG_TO_DEFECT_TYPE.values():
        assert adapter.validate_python(defect_type) == defect_type

REQUEST = {
    "inspection_id": 1,
    "image_key": "runs/1/a.png",
    "image_url": "http://example/x",
}

@pytest.fixture(autouse=True)
def mock_image_download(monkeypatch):
    monkeypatch.setattr(
        main,
        "download_image",
        lambda image_url: b"fake-image-bytes",
    )
    monkeypatch.setattr(main, "perf_counter", lambda: 100.0)


def test_pass_response(monkeypatch):
    monkeypatch.setattr(main, "LATENCY_MS", 0)
    monkeypatch.setattr(main.CT_ADAPTER, "reject_rate", 0.0)
    monkeypatch.setattr(main.CT_ADAPTER, "fail_rate", 0.0)

    response = client.post("/infer/ct", json=REQUEST)

    assert response.status_code == 200
    assert response.json() == {
        "inspection_id": 1,
        "label": "PASS",
        "confidence": 1.0,
        "defects": [],
        "latency_ms": 0,
    }


def test_ct_reject_returns_only_micro_defect(monkeypatch):
    monkeypatch.setattr(main, "LATENCY_MS", 0)
    monkeypatch.setattr(main.CT_ADAPTER, "reject_rate", 1.0)
    monkeypatch.setattr(main.CT_ADAPTER, "fail_rate", 0.0)

    response = client.post("/infer/ct", json=REQUEST)
    body = response.json()

    assert response.status_code == 200
    assert body["label"] == "REJECT"
    assert isinstance(body["defects"], list)
    assert body["defects"][0]["defectType"] == "MICRO_DEFECT"
    assert "defect_type" not in body
    assert "bbox" not in body


def test_rgb_reject_returns_only_rgb_defects(monkeypatch):
    monkeypatch.setattr(main, "LATENCY_MS", 0)
    monkeypatch.setattr(main.RGB_ADAPTER, "reject_rate", 1.0)
    monkeypatch.setattr(main.RGB_ADAPTER, "fail_rate", 0.0)

    for _ in range(20):
        response = client.post("/infer/rgb", json=REQUEST)
        body = response.json()

        assert response.status_code == 200
        assert body["label"] == "REJECT"
        assert body["defects"][0]["defectType"] in {"CRACK", "SPOT"}


def test_fail_response(monkeypatch):
    monkeypatch.setattr(main, "LATENCY_MS", 0)
    monkeypatch.setattr(main.CT_ADAPTER, "reject_rate", 0.0)
    monkeypatch.setattr(main.CT_ADAPTER, "fail_rate", 1.0)

    response = client.post("/infer/ct", json=REQUEST)

    assert response.status_code == 200
    assert response.json() == {
        "inspection_id": 1,
        "label": "FAIL",
        "confidence": 0.0,
        "defects": [],
        "latency_ms": 0,
    }


def test_latency_includes_internal_processing_time(monkeypatch):
    ticks = iter([100.0, 100.125])
    monkeypatch.setattr(main, "perf_counter", lambda: next(ticks))
    monkeypatch.setattr(main, "LATENCY_MS", 0)
    monkeypatch.setattr(main.CT_ADAPTER, "reject_rate", 0.0)
    monkeypatch.setattr(main.CT_ADAPTER, "fail_rate", 0.0)

    response = client.post("/infer/ct", json=REQUEST)

    assert response.status_code == 200
    assert response.json()["latency_ms"] == 125
