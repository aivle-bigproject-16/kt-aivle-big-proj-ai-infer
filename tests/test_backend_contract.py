from datetime import datetime, timezone
from dataclasses import replace

from fastapi.testclient import TestClient

import main
from cell_analysis import build_callback, send_callback
from schemas import CellAnalysisRequest


client = TestClient(main.app)

REQUEST = {
    "requestId": "request-1",
    "batchId": 10,
    "inspectionId": 20,
    "batteryCellId": 30,
    "cellSerialNo": "CELL-30",
    "requestedAt": datetime.now(timezone.utc).isoformat(),
    "callbackUrl": "http://backend:8080/internal/ai/callbacks/cell",
    "images": [{
        "imageId": 40,
        "imageType": "RGB",
        "bucketName": "image-bucket",
        "objectKey": "rgb/image.jpg",
    }],
}


class RecordingExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, task):
        self.calls.append(task)
        return RecordingFuture()


class RecordingFuture:
    def __init__(self):
        self.callback = None

    def add_done_callback(self, callback):
        self.callback = callback


def test_backend_request_is_accepted_with_exact_camel_case_contract(monkeypatch):
    executor = RecordingExecutor()
    monkeypatch.setattr(main, "ANALYSIS_EXECUTOR", executor)
    monkeypatch.setattr(main, "ANALYSIS_CAPACITY", main.BoundedSemaphore(4))
    monkeypatch.setattr(
        main,
        "SETTINGS",
        replace(
            main.SETTINGS,
            internal_api_key="test-key",
            backend_callback_url=REQUEST["callbackUrl"],
        ),
    )

    response = client.post(
        "/ai/cells/analyze",
        json=REQUEST,
        headers={"X-Internal-Api-Key": "test-key"},
    )

    assert response.status_code == 202
    assert response.json().keys() == {
        "accepted",
        "requestId",
        "inspectionId",
        "batteryCellId",
        "status",
        "acceptedAt",
    }
    assert response.json()["accepted"] is True
    assert response.json()["requestId"] == "request-1"
    assert response.json()["status"] == "ACCEPTED"
    assert len(executor.calls) == 1


def test_backend_request_rejects_missing_or_wrong_internal_key(monkeypatch):
    monkeypatch.setattr(
        main,
        "SETTINGS",
        replace(
            main.SETTINGS,
            internal_api_key="test-key",
            backend_callback_url=REQUEST["callbackUrl"],
        ),
    )

    assert client.post("/ai/cells/analyze", json=REQUEST).status_code == 401
    assert client.post(
        "/ai/cells/analyze",
        json=REQUEST,
        headers={"X-Internal-Api-Key": "wrong"},
    ).status_code == 401


class FixedAdapter:
    def __init__(self, prediction):
        self.prediction = prediction

    def predict(self, image_bytes):
        return self.prediction


def test_callback_matches_backend_dto_and_reject_wins(monkeypatch):
    monkeypatch.setattr(
        "cell_analysis.download_s3_image",
        lambda bucket, key: b"image",
    )
    request = CellAnalysisRequest.model_validate({
        **REQUEST,
        "images": [
            {**REQUEST["images"][0], "imageType": "RGB"},
            {
                "imageId": 41,
                "imageType": "CT",
                "bucketName": "image-bucket",
                "objectKey": "ct/image.jpg",
            },
        ],
    })
    callback = build_callback(request, {
        "RGB": FixedAdapter({
            "label": "REJECT",
            "confidence": 0.9,
            "defects": [{
                "defectType": "CRACK",
                "confidence": 0.9,
                "bbox": {"x": 1, "y": 2, "width": 3, "height": 4},
            }],
        }),
        "CT": FixedAdapter({
            "label": "PASS",
            "confidence": 1.0,
            "defects": [],
        }),
    })

    body = callback.model_dump(mode="json", by_alias=True)
    assert body["cellStatus"] == "COMPLETED"
    assert body["finalLabel"] == "REJECT"
    assert body["confidence"] == 0.9
    assert body["imageResults"][0]["defects"][0]["defectType"] == "CRACK"
    assert body["imageResults"][0]["defects"][0]["bbox"] == {
        "x": 1,
        "y": 2,
        "width": 3,
        "height": 4,
    }
    assert body["imageResults"][0]["rawResponse"]["label"] == "REJECT"


def test_operational_image_failure_marks_cell_failed(monkeypatch):
    def fail_download(bucket, key):
        from downloader import ImageDownloadError

        raise ImageDownloadError("not found")

    monkeypatch.setattr("cell_analysis.download_s3_image", fail_download)
    request = CellAnalysisRequest.model_validate(REQUEST)
    callback = build_callback(request, {
        "RGB": FixedAdapter({}),
        "CT": FixedAdapter({}),
    })

    body = callback.model_dump(mode="json", by_alias=True)
    assert body["cellStatus"] == "FAILED"
    assert body["finalLabel"] == "FAIL"
    assert body["imageResults"][0]["errorCode"] == "IMAGE_DOWNLOAD_FAILED"


def test_callback_posts_backend_camel_case_contract_and_internal_key(
    monkeypatch,
):
    request = CellAnalysisRequest.model_validate(REQUEST)
    callback = build_callback(request, {"RGB": None, "CT": None})
    recorded = {}

    class Response:
        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        recorded["url"] = url
        recorded.update(kwargs)
        return Response()

    monkeypatch.setattr("cell_analysis.httpx.post", fake_post)

    send_callback(
        request.callback_url,
        callback,
        "internal-key",
        timeout_seconds=10,
        max_attempts=1,
    )

    assert recorded["url"] == REQUEST["callbackUrl"]
    assert recorded["headers"] == {
        "X-Internal-Api-Key": "internal-key",
    }
    assert recorded["json"]["requestId"] == "request-1"
    assert recorded["json"]["imageResults"][0]["imageId"] == 40


def test_request_rejects_unconfigured_callback_destination(monkeypatch):
    executor = RecordingExecutor()
    monkeypatch.setattr(main, "ANALYSIS_EXECUTOR", executor)
    monkeypatch.setattr(main, "ANALYSIS_CAPACITY", main.BoundedSemaphore(4))
    monkeypatch.setattr(
        main,
        "SETTINGS",
        replace(
            main.SETTINGS,
            internal_api_key="test-key",
            backend_callback_url="http://backend:8080/internal/ai/callbacks/cell",
        ),
    )
    untrusted = {**REQUEST, "callbackUrl": "http://attacker.example/capture"}

    response = client.post(
        "/ai/cells/analyze",
        json=untrusted,
        headers={"X-Internal-Api-Key": "test-key"},
    )

    assert response.status_code == 400
    assert executor.calls == []
