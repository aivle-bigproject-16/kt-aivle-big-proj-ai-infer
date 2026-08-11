"""두 API 계약이 함께 쓰는 값 타입."""
from typing import Literal

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


def to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class BackendContractModel(BaseModel):
    """BE 와 주고받는 모델의 공통 설정.

    필드는 파이썬 쪽에서 snake_case 로 쓰고, 와이어에서는 camelCase 로 나간다.
    `extra="forbid"` 라 계약에 없는 필드가 오면 요청이 거절된다.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class BoundingBox(BaseModel):
    """단건 추론 응답의 좌표. 원본 이미지 좌표계이며 실수다."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    width: float = Field(ge=0.0)
    height: float = Field(ge=0.0)


class CallbackBoundingBox(BackendContractModel):
    """셀 분석 콜백의 좌표. BE DTO 에 맞춰 정수로 반올림해서 보낸다."""

    x: int
    y: int
    width: int = Field(ge=0)
    height: int = Field(ge=0)
