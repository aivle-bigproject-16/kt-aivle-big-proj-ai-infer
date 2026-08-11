"""`POST /infer/ct` · `POST /infer/rgb` 의 요청·응답 계약.

이미지 한 장을 동기로 판정하는 경로다. 필드 표기는 snake_case 그대로 나간다
(셀 분석 계약의 camelCase 와 다르다).
"""
from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.common import BoundingBox, DefectType, Label


class InferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inspection_id: int
    image_key: str = Field(min_length=1)
    image_url: str = Field(min_length=1)


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
