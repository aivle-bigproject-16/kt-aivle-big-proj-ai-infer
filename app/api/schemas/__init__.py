"""와이어 계약 모델. 이 패키지 밖에서 API 표기를 정의하지 않는다.

- `common` — 두 계약이 함께 쓰는 값 타입 (`Label` · `DefectType` · bbox)
- `infer` — `/infer/ct` · `/infer/rgb` 단건 추론
- `cells` — `/ai/cells/analyze` 와 BE 콜백
"""
from app.api.schemas.cells import (
    CallbackDefect,
    CellAnalysisAccepted,
    CellAnalysisCallback,
    CellAnalysisRequest,
    CellImageRequest,
    ImageAnalysisResult,
)
from app.api.schemas.common import (
    BackendContractModel,
    BoundingBox,
    CallbackBoundingBox,
    DefectType,
    Label,
)
from app.api.schemas.infer import Defect, InferRequest, InferResponse


__all__ = [
    "BackendContractModel",
    "BoundingBox",
    "CallbackBoundingBox",
    "CallbackDefect",
    "CellAnalysisAccepted",
    "CellAnalysisCallback",
    "CellAnalysisRequest",
    "CellImageRequest",
    "Defect",
    "DefectType",
    "ImageAnalysisResult",
    "InferRequest",
    "InferResponse",
    "Label",
]
