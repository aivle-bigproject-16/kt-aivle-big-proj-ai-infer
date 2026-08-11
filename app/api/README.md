# API 레이어 — 리뷰어 안내

BE·인프라 담당이 **이 폴더만** 읽으면 서버의 대외 계약 전부를 확인할 수 있습니다.
바깥의 코드(`app/adapters`, `app/vendor`, `app/download`)는 모델과 런타임 구현이며
와이어 표기를 바꾸지 못합니다.

## 무엇이 어디에 있는가

| 궁금한 것 | 볼 파일 |
| --- | --- |
| 엔드포인트 목록과 메서드 | `routers/infer.py` · `routers/cells.py` · `routers/health.py` |
| 요청·응답 본문 필드 | `schemas/infer.py` · `schemas/cells.py` · `schemas/common.py` |
| 어떤 실패가 몇 번으로 나가는가 | `errors.py` (표 하나에 전부) |
| 인증과 콜백 목적지 검증 | `deps.py` · `routers/cells.py` |
| 스펙 전문 | [`../../docs/openapi.json`](../../docs/openapi.json) |

## 리뷰 시 봐야 할 경계

- **표기 규칙이 두 가지입니다.** `/infer/*` 는 snake_case(`inspection_id`),
  `/ai/cells/analyze` 와 콜백은 camelCase(`inspectionId`)입니다. 후자는
  `schemas/common.py` 의 `BackendContractModel` 이 별칭을 자동 생성합니다.
- **모든 모델이 `extra="forbid"`** 입니다. 계약에 없는 필드가 오면 422 로 거절합니다.
  BE 가 필드를 추가하려면 이쪽 스키마도 함께 바뀌어야 합니다.
- **`defectType` 은 영문 4종 고정**입니다(`schemas/common.py`). 모델이 내는 한글
  태그는 어댑터 경계에서 변환되므로 API 밖으로 한글이 나가지 않습니다.
- **`FAIL` 은 에러가 아닙니다.** 촬영불량으로 걸러진 이미지에 대한 정상 200 응답입니다.
- **콜백은 서버가 BE 로 보내는 요청**입니다. `routers/cells.py` 의
  `callback_router` 에 선언돼 있고, `docs/openapi.json` 의 `callbacks` 항목으로도
  나옵니다.

## 계약을 바꿀 때

1. `schemas/` 또는 `routers/` 를 고칩니다.
2. `python -m scripts.dump_openapi` 로 `docs/openapi.json` 을 갱신합니다.
3. `pytest -q` 를 돌립니다. `tests/test_openapi_spec.py` 가 스펙 파일이 코드와
   어긋나면 실패하므로, 갱신을 빠뜨린 채로는 CI 가 통과하지 않습니다.

## 이 폴더가 하지 않는 것

추론 자체, 모델 적재, 이미지 다운로드는 여기 없습니다.

- 판정 로직 → `app/services/inference.py` · `app/services/cell_analysis.py`
- 모델 어댑터 → `app/adapters/`
- 어댑터 적재와 스레드풀 → `app/core/runtime.py`
