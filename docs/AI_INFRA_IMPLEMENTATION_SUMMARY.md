# AI 추론 인프라 구축 진행 및 아키텍처 정리

## 1. 문서 목적

이 문서는 `kt-aivle-big-proj-ai-infer`의 AI 추론 서버와 AWS 검증 인프라가 어떤 순서와 기준으로 구축됐는지 한 문서에서 파악하기 위한 기록이다. 모델 준비, ONNX 변환, 서버 구조, 배포 아티팩트, AWS 구성, 검증 결과, 현재 결정사항과 보류사항을 포함한다.

기준 브랜치는 `feat/onnx-inference-server`, 대상 PR은 `#2`이다.

## 2. 현재 상태 요약

| 항목 | 상태 |
| --- | --- |
| FastAPI CT/RGB 통합 추론 서버 | 구현 완료 |
| CT 품질 모델 ONNX 변환·검증 | 완료 |
| CT 결함 모델 ONNX 변환·검증 | 완료 |
| RGB 품질 모델 ONNX 변환·검증 | 완료 |
| RGB 결함 OWLv2 ONNX 변환·검증 | 구현 및 GPU 스모크 검증 완료 |
| 모델 번들 S3 게시 | 완료 |
| CUDA 12.8 GPU 런타임 ECR 게시 | 완료 |
| NVIDIA L40S GPU 통합검증 | 완료 |
| GitHub Actions CI | 테스트 및 Docker 빌드 통과 |
| 상시 운영 EC2 배포 | 현재 범위 아님 |
| 백엔드 연동 | 현재 범위 이후 작업 |

최종 GPU 검증에서는 CT/RGB가 모두 `CUDAExecutionProvider` 경로로 실행됐고 `/infer/ct`, `/infer/rgb`가 HTTP 200을 반환했다.

## 3. 전체 진행 순서

### 3.1 스텁 서버와 계약 선확정

1. FastAPI 스텁 서버를 먼저 구현했다.
2. `/health`, `/infer/ct`, `/infer/rgb` 엔드포인트와 요청·응답 스키마를 고정했다.
3. GitHub Actions에서 테스트와 Docker 빌드를 수행하도록 구성했다.
4. GHCR에 멀티 아키텍처 스텁 이미지를 게시하고 EC2에서 CT/RGB API 호출을 검증했다.

이 단계의 목적은 실제 모델 연결 전에 백엔드와 AI 서버 사이의 HTTP 계약 및 컨테이너 실행 경로를 먼저 검증하는 것이었다.

### 3.2 모델 레포 검토와 배포 정보 수집

모델 레포의 모델카드, 명세, 노트북, 가중치, 골든 픽스처를 확인했다.

- CT 품질: PyTorch 체크포인트 및 24개 골든 로그잇 픽스처
- CT 결함: YOLO11m-seg 체크포인트, CT 이미지 골든/배포 픽스처
- RGB 품질: Keras 분류 모델
- RGB 결함: OWLv2 기반 외관 결함 탐지 파이프라인

모델카드와 실제 실행 코드가 다를 때는 임의로 계약을 바꾸지 않고, 실제 모델 재현 결과를 기준으로 검증한 뒤 확인이 필요한 항목을 별도 보류사항으로 분리했다.

### 3.3 ONNX 변환 및 로컬 회귀검증

- CT 품질 모델은 PyTorch와 ONNX 로그잇을 비교해 24/24 픽스처를 통과했다.
- RGB 품질 모델은 21개 실제 이미지에서 Keras와 ONNX의 라벨이 모두 일치했다.
- CT 결함 모델은 `task=segment`, 입력 `1280x1280`, opset 17로 변환했다.
- CT 결함은 20개 픽스처에서 ONNX 회귀검증을 수행했다.
- RGB 결함 OWLv2는 ONNX 그래프와 외부 데이터 파일로 분리해 저장했다.
- 실제 API 컨테이너에서 CT/RGB 통합 호출을 로컬로 검증했다.

### 3.4 모델과 컨테이너 배포 아티팩트 분리

대용량 ONNX 모델은 Git에 커밋하지 않고 S3에서 버전 단위로 관리하도록 결정했다.

- S3 모델 번들: `s3://kt-aivle-big-proj-kks/models/ai-infer/onnx-20260809-01/`
- 모델 매니페스트: `model-manifest.json`
- 컨테이너 이미지: `<AWS_ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com/kt-aivle-big-proj-ai-infer:onnx-cuda12-ort126`
- 최종 이미지 digest: `sha256:7ecd8ae6820417638a254c0bcbbfc66940313fd023e724165b9bfc94b5c77883`

모델 다운로드 시 매니페스트의 크기와 SHA-256을 검증하고, 경로가 지정된 모델 디렉터리 밖으로 벗어나지 못하도록 제한했다.

### 3.5 AWS 사전 준비

- 리전: `ap-northeast-2`
- GPU 검증 인스턴스: `g6e.xlarge`
- GPU: NVIDIA L40S
- 루트 볼륨: 150 GiB, gp3, 암호화, 인스턴스 종료 시 삭제
- 접속: Systems Manager Session Manager
- 보안 그룹: 인바운드 없음, 아웃바운드만 허용
- IAM 인스턴스 프로파일: SSM, 제한된 S3 모델 읽기, ECR 이미지 pull 권한
- S3: 버전 관리 활성화, 퍼블릭 액세스 차단
- GPU On-Demand 할당량: 8 vCPU 확보

EC2 생성·검증·종료 스크립트는 기본적으로 DRY RUN이며, 명시적으로 `-Execute`를 전달해야만 비용 발생 작업을 수행하도록 만들었다.

### 3.6 GPU 통합검증

GPU 검증은 다음 순서로 수행했다.

1. `nvidia-smi`로 GPU 확인
2. S3 모델 번들 다운로드 및 SHA-256 검증
3. ECR GPU 이미지 pull
4. PyTorch CUDA 접근 확인
5. ONNX Runtime CUDA provider 실제 로드 확인
6. CT 품질 모델 GPU 직접 추론
7. CT 결함 모델+SAHI GPU 직접 추론
8. FastAPI 실행
9. CT/RGB API 호출 및 응답 계약 검사
10. 성공·실패와 관계없이 임시 EC2와 EBS 삭제

## 4. AI 추론 서버 아키텍처

```text
Backend / 검증 클라이언트
        |
        | POST /infer/ct 또는 POST /infer/rgb
        | inspection_id, image_key, image_url
        v
FastAPI
        |
        v
이미지 다운로더
  - presigned URL 등 HTTP(S) 이미지 다운로드
  - 다운로드 실패 시 502 반환
        |
        v
모달리티별 InferencePipeline
        |
        +--> 품질 모델
        |      |
        |      +--> FAIL: 결함 모델을 실행하지 않고 즉시 반환
        |      |
        |      +--> PASS
        |             |
        |             v
        +--------> 결함 모델
                       |
                       v
              PASS 또는 REJECT + defects
```

### 4.1 공통 API 계약

요청:

```json
{
  "inspection_id": 3001,
  "image_key": "validation/ct.jpg",
  "image_url": "https://..."
}
```

응답:

```json
{
  "inspection_id": 3001,
  "label": "REJECT",
  "confidence": 0.26,
  "defects": [
    {
      "defectType": "MICRO_DEFECT",
      "confidence": 0.26,
      "bbox": {
        "x": 262.0,
        "y": 2250.0,
        "width": 3.0,
        "height": 470.0
      }
    }
  ],
  "latency_ms": 2657
}
```

`label`은 `PASS`, `REJECT`, `FAIL` 중 하나다. `FAIL`은 촬영/입력 품질 단계 실패이며, `REJECT`는 품질은 통과했지만 결함이 검출된 경우다.

### 4.2 CT 파이프라인

1. CT 품질 ONNX 분류기로 입력 적합성을 판정한다.
2. 품질이 `PASS`이면 YOLO11m-seg CT 결함 ONNX를 실행한다.
3. SAHI로 큰 CT 이미지를 슬라이스 추론한다.
4. `porosity` 검출을 API 계약의 `MICRO_DEFECT`로 변환한다.

현재 검증 설정:

- 모델 task: `segment`
- 모델 입력: `1280x1280`
- SAHI slice: `1280x1280`
- overlap: 0.2
- confidence threshold: 0.05
- postprocess: `NMS`
- match metric: `IOS`
- match threshold: `0.44`

### 4.3 RGB 파이프라인

1. RGB 품질 ONNX 분류기로 촬영 품질을 판정한다.
2. 품질이 `PASS`이면 OWLv2 ONNX 외관 결함 탐지를 실행한다.
3. processor/tokenizer 설정으로 텍스트 쿼리와 이미지를 전처리한다.
4. 모델이 반환한 결함 후보 문자열과 bbox를 API 응답으로 변환한다.

RGB 결함 유형은 서버에서 `CRACK`, `SPOT` 등으로 임의 매핑하지 않고 모델 원본 출력값을 보존하기로 결정했다. DB 및 백엔드는 임의의 모델 결함 문자열을 저장할 수 있어야 한다.

#### Qwen2.5-VL 적용 범위

RGB 모델카드의 상위 구조는 `OWLv2 검출 → Qwen2.5-VL 해설`로 표현돼 있다. 이는 두 모델을 하나로 병합한 단일 모델이 아니라 OWLv2가 검출한 후보를 Qwen이 추가 해설하는 순차 파이프라인이다.

현재 AI 서버에는 판정에 참여하는 OWLv2만 ONNX로 배포했으며 Qwen2.5-VL은 포함하지 않았다. 이 결정은 Qwen을 실수로 누락한 것이 아니라 모델 레포의 실제 배포 모듈 `ext_infer.py`와 상세 모델카드에 명시된 다음 조건을 따른 것이다.

- PASS/REJECT 판정은 OWLv2의 검출 박스 개수만 사용한다.
- Qwen은 판정에 영향을 주지 않는 선택적 설명 단계다.
- Qwen의 유형·등급 출력은 모델팀 검증에서 배포 기준을 충족하지 못했다.
- 배포용 `ext_infer.py`에는 Qwen 실행 코드와 `use_vlm` 스위치가 없고, 필요한 경우 평가 노트북에서만 실행한다.
- 따라서 현재 S3 모델 번들, ECR 이미지와 API 응답에는 Qwen 가중치 및 출력이 없다.

현재 RGB 서버를 정확히 표현하면 "운영 판정에 사용되는 OWLv2 단계만 ONNX로 배포한 서버"다. 추후 Qwen을 추가하려면 Qwen 가중치 배포 방식, GPU 메모리, 실행 조건, 응답 계약, 지연 목표와 정식 골든 데이터를 별도로 확정하고 두 번째 추론 단계로 구현해야 한다.

### 4.4 런타임 구조

- 베이스 이미지: `pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime`
- PyTorch: 2.11.0+cu128
- ONNX Runtime GPU: 1.26.0
- FastAPI + Uvicorn
- SAHI + Ultralytics 8.4.115
- Transformers 5.14.1

서버 시작 전에 PyTorch CUDA 라이브러리를 로드하고 `onnxruntime.preload_dlls()`를 실행한다. 이후 실제 CUDA provider 공유 라이브러리를 로드한 다음 FastAPI를 시작한다.

## 5. 주요 문제와 해결 과정

### 5.1 CT 입력 크기와 골든 검증 혼선

CT 문서와 실행 경로에서 640/1280 설명이 혼재했다. 실제 체크포인트와 검증 경로를 확인한 결과 최종 배포 검증은 입력 1280과 `task=segment` 기준으로 수행했다.

### 5.2 CT ONNX 중복 검출

기존 `NMS + IOU@0.5`에서는 일부 세로로 긴 결함이 중복 검출됐다. `NMS + IOS@0.44`에서 20개 픽스처가 모두 판정·개수·confidence 기준을 통과했다. 이 값은 현재 검증용 운영 설정에 적용돼 있다.

### 5.3 잘못된 CT 통합 픽스처

초기 `golden_ct.jpg`는 CT 품질 모델에서 `FAIL`로 차단돼 결함 모델이 실행되지 않았다. 품질과 결함 파이프라인을 모두 통과하는 배포 픽스처 `CT__CT_cell_pouch_101_y_043__8c633842.jpg`로 교체했다.

### 5.4 CUDA와 ONNX Runtime 버전 불일치

초기 GPU 이미지의 ONNX Runtime 1.28.0은 CUDA 13용이었으나 베이스 이미지는 CUDA 12.8이었다. `libcublasLt.so.13` 누락으로 CUDA provider 생성이 실패하고 CPU로 폴백했다.

해결:

- ONNX Runtime GPU를 1.26.0으로 고정
- PyTorch CUDA 12.8 및 cuDNN 9와 정렬
- `onnxruntime.preload_dlls()` 적용
- provider 이름 확인뿐 아니라 CUDA provider 라이브러리 실제 로드 검사 추가

### 5.5 실패 로그와 정리 자동화

- API 500 발생 시 Docker traceback이 누락되지 않도록 종료 trap과 컨테이너 로그 출력을 추가했다.
- Windows CP949로 SSM 로그가 잘리는 문제를 막기 위해 UTF-8 환경을 고정했다.
- 종료 후 이미 삭제된 EBS 조회가 오류로 처리되지 않도록 종료 스크립트를 보완했다.
- 인스턴스 Name, 타입, 상태, SSM Online을 검증한 후에만 원격 명령을 실행한다.

## 6. 최종 GPU 검증 결과

| 검사 | 결과 |
| --- | --- |
| 모델 번들 8개 파일 무결성 | PASS |
| NVIDIA L40S 인식 | PASS |
| CUDAExecutionProvider 로드 | PASS |
| CT 품질 GPU 직접 추론 | PASS |
| CT 결함+SAHI GPU 직접 추론 | PASS |
| CT FastAPI 호출 | HTTP 200 / PASS |
| RGB FastAPI 호출 | HTTP 200 / PASS |
| CT 응답 | REJECT, MICRO_DEFECT 1건 |
| CT API latency | 약 2.7초 |
| RGB API latency | 약 3.0초 |
| 최종 GPU ONNX 검증 | PASS |

`/sys/class/drm/card0` 탐색 경고와 CUDA 그래프 관련 Memcpy 경고가 있었지만, 실제 세션은 CUDA provider로 실행됐으며 CT/RGB API 결과에는 영향을 주지 않았다.

## 7. 현재 결정사항

1. 실제 모델 배포 포맷은 ONNX를 사용한다.
2. 모델 파일은 Git이 아니라 버전이 지정된 S3 번들로 관리한다.
3. 컨테이너 이미지는 ECR에서 불변 태그와 digest로 식별한다.
4. API 서버는 품질 우선 파이프라인을 사용한다.
5. 품질 `FAIL`이면 결함 모델을 실행하지 않는다.
6. CT 결함 모델은 `task=segment`, 입력 1280으로 실행한다.
7. CT 검증 설정은 임시로 `NMS + IOS@0.44`를 사용한다.
8. RGB 결함 유형은 서버에서 임의 변환하지 않고 모델 원본 문자열을 반환한다.
9. RGB 서버는 현재 OWLv2 판정 단계만 배포하며 선택적 Qwen 해설 단계는 포함하지 않는다.
10. GPU 검증 인프라는 필요할 때만 생성하고 검증 후 즉시 삭제한다.
11. 상시 운영 배포와 백엔드 연동은 별도 단계로 진행한다.

## 8. 보류 및 후속 확인사항

- **보류: RGB 모델 레포의 `golden_fixture_deploy.json`이 참조하는 정식 원본 이미지 세트가 없다. 현재 GPU 결과는 실제 이미지 기반 스모크 검증이며 정식 골든 회귀검증은 아니다. AI팀에서 원본 이미지, 기대 판정, 결함 유형과 허용 오차를 제공해야 한다.**

- **보류: CT의 `NMS + IOS@0.44`는 20개 픽스처를 통과했지만 기존 문서의 `NMS + IOU`와 다르다. AI팀이 IOS 사용 및 최종 threshold를 승인해야 하며, 승인 후 모델카드와 운영 명세를 동기화해야 한다.**

- **보류: RGB 모델 코드와 API 출력에서 한국어 결함 유형 문자열이 mojibake 형태로 저장·출력되고 있다. 단순 콘솔 문제가 아니라 현재 소스 상수에도 깨진 문자열이 포함되어 있으므로, 원본 한글 라벨을 AI팀과 확인한 뒤 UTF-8 문자열로 복구하고 계약 테스트를 다시 수행해야 한다.**

- **보류: Qwen2.5-VL은 현재 배포 서버에서 제외했다. 향후 Qwen 해설이 실제 서비스 요구사항이라면 AI팀이 적용 목적, 호출 대상 후보, 출력 계약, 골든 결과와 허용 오차를 먼저 확정해야 하며, 그 전에는 현재 OWLv2 전용 경로를 유지한다.**

- **보류: 최종 GPU 검증용 임시 EC2는 종료 요청 후 `terminated`, EBS는 삭제 상태까지 확인해야 한다. 상태 확인이 끝난 뒤 비용 정리 완료로 기록한다.**

- **후속 범위: 백엔드 연동, 상시 서비스용 네트워크/오토스케일링, 모니터링·알람, 운영 배포 방식은 이번 검증 범위에 포함하지 않았다.**

## 9. 운영 전 체크리스트

- [ ] RGB 정식 골든 이미지와 기대 결과 수령
- [ ] CT IOS@0.44 운영 승인
- [ ] RGB 한글 결함 문자열 복구
- [ ] Qwen2.5-VL 서비스 적용 여부 및 출력 계약 확정
- [ ] 임시 GPU EC2 및 EBS 삭제 확인
- [ ] PR #2 CI 최종 통과 및 리뷰
- [ ] `main` 병합
- [ ] 백엔드에 API 계약, ECR 이미지, S3 번들, 환경변수 전달
- [ ] 상시 운영 배포 설계 확정

## 10. 주요 파일

| 파일 | 역할 |
| --- | --- |
| `app/main.py` | FastAPI 엔드포인트 및 공통 추론 처리 |
| `app/adapters/base.py` | 품질 우선 파이프라인 |
| `app/adapters/factory.py` | CT/RGB 및 CPU/GPU 어댑터 조립 |
| `app/adapters/ct_quality_onnx.py` | CT 품질 ONNX 전처리·추론 |
| `app/adapters/ct_defect_onnx.py` | CT YOLO-seg+SAHI ONNX 추론 |
| `app/adapters/rgb_quality_onnx.py` | RGB 품질 ONNX 전처리·추론 |
| `app/vendor/rgb_ext_infer_onnx.py` | RGB OWLv2 ONNX 추론 |
| `app/adapters/rgb_defect_owlv2.py` | RGB 모델 결과를 API 계약으로 변환 |
| `app/gpu_runtime.py` | CUDA/cuDNN preload 후 FastAPI 시작 |
| `docker/Dockerfile.gpu-onnx` | 통합 GPU 런타임 이미지 |
| `deployment/model-manifest.json` | S3 모델 번들 무결성 명세 |
| `scripts/run-gpu-validation.ps1` | GPU 직접·API 통합검증 |
| `scripts/launch-gpu-validation.ps1` | 임시 GPU EC2 생성 |
| `scripts/terminate-gpu-validation.ps1` | 임시 GPU EC2/EBS 삭제 |
