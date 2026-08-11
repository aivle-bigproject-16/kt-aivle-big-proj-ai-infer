# kt-aivle-big-proj-ai-infer

[![CI](https://github.com/aivle-bigproject-16/kt-aivle-big-proj-ai-infer/actions/workflows/ci.yml/badge.svg)](https://github.com/aivle-bigproject-16/kt-aivle-big-proj-ai-infer/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com/)
[![ONNX Runtime](https://img.shields.io/badge/ONNX%20Runtime-1.x-005CED)](https://onnxruntime.ai/)

KT AIVLE 빅프로젝트 16조 **AI 추론 서버**입니다. 배터리 셀의 CT·RGB 이미지를 받아
촬영불량 분류와 결함 검출을 수행하고, 계약에 고정된 4종 `defectType`으로 결과를
반환합니다. 배치 오케스트레이션과 셀 판정 저장은 BE 책임입니다.

## 📁 저장소 구조

- `app/` — 서비스 코드 (파이썬 패키지)
  - `main.py` — FastAPI 엔드포인트와 공통 추론 처리
  - `settings.py` · `schemas.py` — 환경변수 로딩, 요청·응답 계약 모델
  - `cell_analysis.py` — 셀 단위 비동기 분석과 BE 콜백 전송
  - `gpu_runtime.py` — CUDA 라이브러리 선로드 후 uvicorn 기동 (GPU 이미지 진입점)
  - `adapters/` — 모달별 어댑터
    - `base.py` — 어댑터 프로토콜, 스텁, 품질 우선 파이프라인
    - `factory.py` — `INFERENCE_MODE`에 따른 어댑터 조립
    - `ct_quality_onnx.py` · `ct_defect_onnx.py` — CT 품질 분류기, YOLO-seg+SAHI
    - `rgb_quality_onnx.py` · `rgb_defect_owlv2.py` — RGB 품질 분류기, OWLv2 계약 변환
  - `download/` — `http_image.py`(presigned URL, SSRF 차단) · `s3_image.py`(S3 직접 조회)
  - `vendor/` — 모델 레포에서 **원본 해시 그대로** 가져온 코드. 수정하지 않습니다
- `docker/` — `Dockerfile`(CPU) · `Dockerfile.gpu-onnx`(GPU). 빌드 컨텍스트는 리포지토리 루트입니다
- `requirements/` — `base` · `dev` · `gpu-onnx` · `rgb-defect-lock` · `rgb-defect-export`
- `scripts/` — GPU 검증, ONNX 변환, 모델 번들 발행 스크립트
- `tests/` — pytest 계약·회귀 테스트
- `deployment/model-manifest.json` — S3 모델 번들 무결성 명세
- `docs/` — 아래 [문서](#-문서) 참조

## 🔌 API

| 엔드포인트 | 설명 |
| --- | --- |
| `POST /infer/ct` | CT 이미지 1장 동기 추론 |
| `POST /infer/rgb` | RGB 이미지 1장 동기 추론 |
| `POST /ai/cells/analyze` | 셀 단위 비동기 분석. `202`를 즉시 반환하고 결과는 콜백으로 보냅니다 |
| `GET /health` | 서버 준비 상태와 모달별 어댑터 상세 |

### 단건 추론 (`/infer/*`)

요청의 `image_url`은 BE가 발급한 presigned URL이며, 서버가 이미지를 직접
다운로드합니다. 사설·루프백·링크로컬 주소로 향하는 URL은 거부합니다.

| 필드 | 값 |
| --- | --- |
| `label` | `PASS` · `REJECT` · `FAIL` |
| `confidence` | 이미지 판정 신뢰도. PASS일 때는 `1 − (임계값 미만 최고 결함 점수)`이고, 후보가 없으면 `1.0`입니다 |
| `defects[]` | 각 원소는 `{ defectType, confidence, bbox }` |
| `defectType` | `SWELLING` · `SPOT` · `MICRO_DEFECT` · `CRACK` 4종 |
| `latency_ms` | 이미지 다운로드를 포함한 요청 처리 전체 시간 |

`FAIL`은 에러가 아니라 촬영불량 분류기가 "처리 불가"로 거른 이미지에 대한 정상
200 응답입니다.

RGB 실모델(OWLv2)은 한글 태그를 내므로 어댑터 경계에서 위 4종으로 변환합니다.
매핑표는 [`docs/RGB_DEFECT_ONNX.md`](docs/RGB_DEFECT_ONNX.md)에 있습니다.

| 코드 | 상황 |
| --- | --- |
| 200 | 추론 성공 (`FAIL` 판정 포함) |
| 422 | 전처리가 이미지를 거부했습니다 |
| 500 | 추론 중 예기치 못한 실패 |
| 502 | `image_url` 다운로드 실패 |
| 503 | 해당 모달 어댑터가 준비되지 않았습니다 |

### 셀 분석 (`/ai/cells/analyze`)

BE는 `X-Internal-Api-Key` 헤더와 함께 셀 분석을 요청합니다. AI 서버는 `202
Accepted`를 즉시 반환한 뒤, 요청에 담긴 CT·RGB 객체를 S3에서 직접 읽어
추론하고, 완료된 셀 결과를 BE 콜백 URL로 POST합니다.

BE API, BE AI 게이트웨이, 이 서비스는 같은 `AI_INTERNAL_API_KEY`를 써야 합니다.
서버는 BE가 보낸 `callbackUrl`이 설정값과 정확히 일치할 때만 요청을 받습니다.

```dotenv
AI_INTERNAL_API_KEY=replace-with-the-shared-secret
BACKEND_CALLBACK_URL=http://backend:8080/internal/ai/callbacks/cell
CELL_ANALYSIS_WORKERS=1
CELL_ANALYSIS_QUEUE_SIZE=4
CALLBACK_TIMEOUT_SECONDS=10
CALLBACK_MAX_ATTEMPTS=3
```

런타임 IAM 역할은 BE가 분석 요청에 담는 모든 `bucketName`·`objectKey`에 대해
`s3:GetObject`를 허용해야 합니다.

전체 환경변수 목록은 [`.env.example`](.env.example)에 있습니다.

## ⚙️ 추론 모드

`INFERENCE_MODE`로 모달별 실모델 사용 여부를 정합니다.

| 모드 | CT | RGB |
| --- | --- | --- |
| `stub` | 스텁 | 스텁 |
| `ct-quality-onnx` | 분류기만 ONNX | 스텁 |
| `quality-onnx` | 분류기만 ONNX | 분류기만 ONNX |
| `ct-onnx` | 전체 ONNX | 스텁 |
| `rgb-onnx` | 스텁 | 전체 ONNX |
| `onnx` | 전체 ONNX | 전체 ONNX |

모델 파일은 이미지에 넣거나 Git에 커밋하지 않고 `/models`에 읽기 전용으로
마운트합니다.

### 이미지별 지원 범위

| 이미지 | 지원 모드 | 비고 |
| --- | --- | --- |
| `docker/Dockerfile` | `stub`, `ct-quality-onnx`, `ct-onnx` | CPU. `transformers`를 넣지 않아 RGB 실모델은 못 씁니다 |
| `docker/Dockerfile.gpu-onnx` | 전체 | CUDA 12.8. `app/gpu_runtime.py`가 CUDA 라이브러리를 선로드합니다 |

지원하지 않는 모드로 뜨면 프로세스가 죽는 대신 `/health`가 `degraded`를 보고하고
해당 모달 추론이 503을 반환합니다.

## 🚀 로컬 실행

```bash
docker build -f docker/Dockerfile -t kt-aivle-big-proj-ai-infer:local .
docker run --rm -p 8000:8000 --env-file .env.example kt-aivle-big-proj-ai-infer:local
```

컨테이너 없이 띄우려면 다음과 같이 실행합니다.

```bash
pip install -r requirements/base.txt
uvicorn app.main:app --reload
```

## 🧪 테스트

```bash
pip install -r requirements/dev.txt
pytest -q
```

## 📦 컨테이너 발행

GitHub Actions의 `Publish container` 워크플로를 수동 실행하고 태그를 입력하면
다음 GHCR 경로에 CPU 이미지가 발행됩니다.

```text
ghcr.io/aivle-bigproject-16/kt-aivle-big-proj-ai-infer:<tag>
```

GPU 이미지는 `scripts/publish-gpu-image.ps1`로 ECR에 발행합니다.

## 📚 문서

| 문서 | 내용 |
| --- | --- |
| [`docs/AI_INFRA_IMPLEMENTATION_SUMMARY.md`](docs/AI_INFRA_IMPLEMENTATION_SUMMARY.md) | AI 인프라 구현 전체 요약과 잔여 과제 |
| [`docs/V0_2_0_FIX_PLAN.md`](docs/V0_2_0_FIX_PLAN.md) | v0.2.0 결함 감사와 수정 계획 |
| [`docs/CT_DEFECT_ONNX.md`](docs/CT_DEFECT_ONNX.md) | CT 결함 ONNX 후처리 설정과 골든 픽스처 검증 결과 |
| [`docs/RGB_DEFECT_ONNX.md`](docs/RGB_DEFECT_ONNX.md) | RGB OWLv2 통합, 결함 유형 매핑표, ONNX 변환 절차 |
| [`docs/DB_RECOMMENDATIONS.md`](docs/DB_RECOMMENDATIONS.md) | `defect_type` 컬럼 제약에 대한 DB·BE 권고 |
| [`docs/AI_TEAM_CONFIRMATION_REQUESTS.md`](docs/AI_TEAM_CONFIRMATION_REQUESTS.md) | AI팀 확인 대기 항목 |
