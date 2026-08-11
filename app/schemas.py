from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Label = Literal["PASS", "REJECT", "FAIL"]

# 계약 §6.5 / A-5: 와이어 표기는 영문 4종 고정이다. 모델이 내는 한글 라벨은
# 어댑터 경계(app.adapters.rgb_defect_owlv2.TAG_TO_DEFECT_TYPE)에서 이 4종으로
# 변환한다.
DefectType = Literal[
    "SWELLING",
    "SPOT",
    "MICRO_DEFECT",
    "CRACK",
]


class InferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inspection_id: int
    image_key: str = Field(min_length=1)
    image_url: str = Field(min_length=1)


class BoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    width: float = Field(ge=0.0)
    height: float = Field(ge=0.0)


class Defect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defectType: DefectType
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BoundingBox


class InferResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inspection_id: int
    label: Label
    confidence: float = Field(ge=0.0, le=1.0)
    defects: list[Defect]
    latency_ms: int = Field(ge=0)


def _to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class BackendContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
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


class CallbackBoundingBox(BackendContractModel):
    x: int
    y: int
    width: int = Field(ge=0)
    height: int = Field(ge=0)


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
