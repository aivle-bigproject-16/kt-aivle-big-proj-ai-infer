from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Label = Literal["PASS", "REJECT", "FAIL"]

# 계약 §6.5 / A-5: 와이어 표기는 영문 4종 고정이다. 모델이 내는 한글 라벨은
# 어댑터 경계(rgb_owlv2_defect.TAG_TO_DEFECT_TYPE)에서 이 4종으로 변환한다.
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
