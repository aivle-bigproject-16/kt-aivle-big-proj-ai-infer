# kt-aivle-big-proj-ai-infer

KT AIVLE 빅프로젝트 16조 AI 추론 서버입니다. 이미지 1장을 받아 `{ label, confidence, defects[] }`를 동기 반환합니다. 배치 오케스트레이션과 셀 판정은 BE 책임입니다.

## API

- `POST /infer/ct`: CT 이미지 추론
- `POST /infer/rgb`: RGB 이미지 추론
- `GET /health`: 서버 준비 상태

요청의 `image_url`은 BE가 발급한 presigned URL이며, 서버가 이미지를 직접 다운로드합니다. 사설·루프백·링크로컬 주소로 향하는 URL은 거부합니다.

### 응답 계약

| 필드 | 값 |
| --- | --- |
| `label` | `PASS` · `REJECT` · `FAIL` |
| `confidence` | 이미지 판정 신뢰도. PASS일 때는 `1 − (임계값 미만 최고 결함 점수)`이고, 후보가 없으면 `1.0`입니다 |
| `defects[]` | 각 원소는 `{ defectType, confidence, bbox }` |
| `defectType` | `SWELLING` · `SPOT` · `MICRO_DEFECT` · `CRACK` 4종 |
| `latency_ms` | 이미지 다운로드를 포함한 요청 처리 전체 시간 |

`FAIL`은 에러가 아니라 촬영불량 분류기가 "처리 불가"로 거른 이미지에 대한 정상 200 응답입니다.

RGB 실모델(OWLv2)은 한글 태그를 내므로 어댑터 경계에서 위 4종으로 변환합니다. 매핑표는 `docs/V0_2_0_FIX_PLAN.md` §2 C-1에 있습니다.

### HTTP 상태 코드

| 코드 | 상황 |
| --- | --- |
| 200 | 추론 성공 (`FAIL` 판정 포함) |
| 422 | 전처리가 이미지를 거부했습니다 |
| 500 | 추론 중 예기치 못한 실패 |
| 502 | `image_url` 다운로드 실패 |
| 503 | 해당 모달 어댑터가 준비되지 않았습니다 |

## 추론 모드

`INFERENCE_MODE`로 모달별 실모델 사용 여부를 정합니다.

| 모드 | CT | RGB |
| --- | --- | --- |
| `stub` | 스텁 | 스텁 |
| `ct-quality-onnx` | 분류기만 ONNX | 스텁 |
| `quality-onnx` | 분류기만 ONNX | 분류기만 ONNX |
| `ct-onnx` | 전체 ONNX | 스텁 |
| `rgb-onnx` | 스텁 | 전체 ONNX |
| `onnx` | 전체 ONNX | 전체 ONNX |

## 이미지별 지원 범위

| 이미지 | 지원 모드 | 비고 |
| --- | --- | --- |
| `Dockerfile` | `stub`, `ct-quality-onnx`, `ct-onnx` | CPU. `transformers`를 넣지 않아 RGB 실모델은 못 씁니다 |
| `Dockerfile.gpu-onnx` | 전체 | CUDA 12.8. `gpu_runtime.py`가 CUDA 라이브러리를 선로드합니다 |

지원하지 않는 모드로 뜨면 프로세스가 죽는 대신 `/health`가 `degraded`를 보고하고 해당 모달 추론이 503을 반환합니다.

## 로컬 실행

```bash
docker build -t kt-aivle-big-proj-ai-infer:local .
docker run --rm -p 8000:8000 --env-file .env.example kt-aivle-big-proj-ai-infer:local
```

## 테스트

```bash
pip install -r requirements-dev.txt
pytest -q
```

## 컨테이너 발행

GitHub Actions의 `Publish container` 워크플로를 수동 실행하고 태그를 입력하면 다음 GHCR 경로에 발행됩니다.

```text
ghcr.io/aivle-bigproject-16/kt-aivle-big-proj-ai-infer:<tag>
```

GPU 이미지는 `scripts/publish-gpu-image.ps1`로 ECR에 발행합니다.
