from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Label = Literal["PASS", "REJECT", "FAIL"]
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
