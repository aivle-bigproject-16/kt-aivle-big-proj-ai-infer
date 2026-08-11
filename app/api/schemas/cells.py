"""`POST /ai/cells/analyze` 요청·수락 응답과, BE 로 되돌려 보내는 콜백 계약.

BE 가 셀 하나(이미지 여러 장)를 맡기면 서버는 `CellAnalysisAccepted` 로 즉시
답하고, 분석이 끝난 뒤 `CellAnalysisCallback` 을 BE 콜백 URL 로 POST 한다.
와이어 표기는 전부 camelCase 다.
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.api.schemas.common import (
    BackendContractModel,
    CallbackBoundingBox,
    DefectType,
    Label,
)


class CellImageRequest(BackendContractModel):
    image_id: int
    image_type: Literal["CT", "RGB"]
    bucket_name: str = Field(min_length=1)
    object_key: str = Field(min_length=1)


class CellAnalysisRequest(BackendContractModel):
    request_id: str = Field(min_length=1)
    batch_id: int
    inspection_id: int
    battery_cell_id: int
    cell_serial_no: str = Field(min_length=1)
    requested_at: datetime
    callback_url: str = Field(min_length=1)
    images: list[CellImageRequest] = Field(min_length=1)


class CellAnalysisAccepted(BackendContractModel):
    accepted: bool
    request_id: str
    inspection_id: int
    battery_cell_id: int
    status: Literal["ACCEPTED"]
    accepted_at: datetime


class CallbackDefect(BackendContractModel):
    defect_type: DefectType
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: CallbackBoundingBox


class ImageAnalysisResult(BackendContractModel):
    image_id: int
    image_type: Literal["CT", "RGB"]
    label: Label
    confidence: float = Field(ge=0.0, le=1.0)
    defects: list[CallbackDefect]
    raw_response: dict[str, Any] | None
    latency_ms: int = Field(ge=0)
    error_code: str | None
    error_message: str | None


class CellAnalysisCallback(BackendContractModel):
    request_id: str
    batch_id: int
    inspection_id: int
    battery_cell_id: int
    cell_serial_no: str
    cell_status: Literal["COMPLETED", "FAILED"]
    final_label: Label | None
    failure_reason: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    completed_at: datetime
    image_results: list[ImageAnalysisResult]
