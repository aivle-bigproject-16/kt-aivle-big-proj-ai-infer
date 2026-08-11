import pytest
from pydantic import TypeAdapter, ValidationError

from app.adapters.rgb_defect_owlv2 import TAG_TO_DEFECT_TYPE
from app.api.schemas import DefectType
from app.core.runtime import AdapterSlot
from app.services import inference


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
        inference,
        "download_image",
        lambda image_url: b"fake-image-bytes",
    )
    monkeypatch.setattr(inference, "perf_counter", lambda: 100.0)


def test_pass_response(monkeypatch, client, runtime):
    monkeypatch.setattr(inference, "LATENCY_MS", 0)
    monkeypatch.setattr(runtime.slot("ct").adapter, "reject_rate", 0.0)
    monkeypatch.setattr(runtime.slot("ct").adapter, "fail_rate", 0.0)

    response = client.post("/infer/ct", json=REQUEST)

    assert response.status_code == 200
    assert response.json() == {
        "inspection_id": 1,
        "label": "PASS",
        "confidence": 1.0,
        "defects": [],
        "latency_ms": 0,
    }


def test_ct_reject_returns_only_micro_defect(monkeypatch, client, runtime):
    monkeypatch.setattr(inference, "LATENCY_MS", 0)
    monkeypatch.setattr(runtime.slot("ct").adapter, "reject_rate", 1.0)
    monkeypatch.setattr(runtime.slot("ct").adapter, "fail_rate", 0.0)

    response = client.post("/infer/ct", json=REQUEST)
    body = response.json()

    assert response.status_code == 200
    assert body["label"] == "REJECT"
    assert isinstance(body["defects"], list)
    assert body["defects"][0]["defectType"] == "MICRO_DEFECT"
    assert "defect_type" not in body
    assert "bbox" not in body


def test_rgb_reject_returns_only_rgb_defects(monkeypatch, client, runtime):
    monkeypatch.setattr(inference, "LATENCY_MS", 0)
    monkeypatch.setattr(runtime.slot("rgb").adapter, "reject_rate", 1.0)
    monkeypatch.setattr(runtime.slot("rgb").adapter, "fail_rate", 0.0)

    for _ in range(20):
        response = client.post("/infer/rgb", json=REQUEST)
        body = response.json()

        assert response.status_code == 200
        assert body["label"] == "REJECT"
        assert body["defects"][0]["defectType"] in {"CRACK", "SPOT"}


def test_fail_response(monkeypatch, client, runtime):
    monkeypatch.setattr(inference, "LATENCY_MS", 0)
    monkeypatch.setattr(runtime.slot("ct").adapter, "reject_rate", 0.0)
    monkeypatch.setattr(runtime.slot("ct").adapter, "fail_rate", 1.0)

    response = client.post("/infer/ct", json=REQUEST)

    assert response.status_code == 200
    assert response.json() == {
        "inspection_id": 1,
        "label": "FAIL",
        "confidence": 0.0,
        "defects": [],
        "latency_ms": 0,
    }


def test_health_reports_the_live_adapters(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["models"] == {"ct": True, "rgb": True}
    assert body["details"]["ct"]["adapter"] == "StubAdapter"
    assert body["details"]["ct"]["error"] is None


def test_health_reports_a_failed_adapter(monkeypatch, client, runtime):
    monkeypatch.setitem(
        runtime.slots,
        "rgb",
        AdapterSlot(None, "RuntimeError: no model"),
    )

    body = client.get("/health").json()

    assert body["status"] == "degraded"
    assert body["models"] == {"ct": True, "rgb": False}
    assert body["details"]["rgb"]["error"] == "RuntimeError: no model"


def test_unavailable_adapter_answers_with_service_unavailable(
    monkeypatch,
    client,
    runtime,
):
    monkeypatch.setitem(
        runtime.slots,
        "ct",
        AdapterSlot(None, "RuntimeError: boom"),
    )

    response = client.post("/infer/ct", json=REQUEST)

    assert response.status_code == 503
    assert "RuntimeError: boom" in response.json()["detail"]


def test_unprocessable_image_answers_with_422(monkeypatch, client, runtime):
    class RejectingAdapter:
        def predict(self, image_bytes):
            raise ValueError("invalid CT image")

    monkeypatch.setattr(inference, "LATENCY_MS", 0)
    monkeypatch.setitem(
        runtime.slots,
        "ct",
        AdapterSlot(RejectingAdapter(), None),
    )

    response = client.post("/infer/ct", json=REQUEST)

    assert response.status_code == 422
    assert response.json()["detail"] == "unprocessable inference image"


def test_unexpected_adapter_failure_answers_with_500(
    monkeypatch,
    client,
    runtime,
):
    class BrokenAdapter:
        def predict(self, image_bytes):
            raise RuntimeError("cuda died")

    monkeypatch.setattr(inference, "LATENCY_MS", 0)
    monkeypatch.setitem(
        runtime.slots,
        "ct",
        AdapterSlot(BrokenAdapter(), None),
    )

    response = client.post(
        "/infer/ct",
        json=REQUEST,
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "inference failed"


def test_download_failure_answers_with_502(monkeypatch, client):
    def fail_download(image_url):
        raise inference.ImageDownloadError("boom")

    monkeypatch.setattr(inference, "LATENCY_MS", 0)
    monkeypatch.setattr(inference, "download_image", fail_download)

    response = client.post("/infer/ct", json=REQUEST)

    assert response.status_code == 502
    assert response.json()["detail"] == "failed to download inference image"


def test_latency_includes_internal_processing_time(
    monkeypatch,
    client,
    runtime,
):
    ticks = iter([100.0, 100.125])
    monkeypatch.setattr(inference, "perf_counter", lambda: next(ticks))
    monkeypatch.setattr(inference, "LATENCY_MS", 0)
    monkeypatch.setattr(runtime.slot("ct").adapter, "reject_rate", 0.0)
    monkeypatch.setattr(runtime.slot("ct").adapter, "fail_rate", 0.0)

    response = client.post("/infer/ct", json=REQUEST)

    assert response.status_code == 200
    assert response.json()["latency_ms"] == 125
