# RGB 결함 모델 통합 상태

## 구현 범위

- 모델 레포 `kt-aivle-big-proj-model-rgb`의 커밋 `09563fc`에서
  `ext_infer.py`와 `ext_requirements.lock.txt`를 원본 해시 그대로 가져왔다.
  서버에서는 각각 `rgb_ext_infer.py`,
  `requirements-rgb-defect.lock.txt`로 관리한다.
- 한 장의 이미지 바이트를 OWLv2의 `infer_frames()`에 전달한다.
- 모델의 원본 좌표계 `bbox=[x1,y1,x2,y2]`를 서버 계약의
  `{x,y,width,height}`로 변환한다.
- 모델의 한국어 `유형후보[0]`을 계약 §6.5의 영문 4종으로 변환해
  `defectType`으로 반환한다.
- 정상 결과는 `PASS`, `defects=[]`로 반환한다. 최상위 `confidence`는
  계약 A-4에 따라 `1 - (임계값 미만 최고 결함 점수)`이며, 후보가 없으면
  `1.0`이다.
- Qwen2.5-VL은 판정에 영향을 주지 않는 설명용 2차 모델이므로 현재 API
  어댑터에는 포함하지 않는다.

## 결함 유형 매핑

모델은 한글 태그를 내고, 서버는 어댑터 경계
(`rgb_owlv2_defect.TAG_TO_DEFECT_TYPE`)에서 계약 값으로 바꾼다.

| OWLv2 태그 | `defectType` |
| --- | --- |
| `파손·찢김` | `CRACK` |
| `긁힘·스크래치` | `CRACK` |
| `녹·부식` | `SPOT` |
| `오염·이물질` | `SPOT` |
| `벗겨짐·박리` | `SWELLING` |
| `들뜸` | `SWELLING` |

`정상:금속캡`은 결함이 아니라 정상 구조물이므로 결함 배열에서 제외한다.
모델의 `DROP_TAGS`가 이 태그를 일부러 남기기 때문에(구조물로 지우면 진짜
결함까지 잃는다) 서버 쪽에서 걸러야 한다.

매핑에 없는 태그가 오면 그 결함 하나만 버리고 경고 로그를 남긴다. 요청
전체를 실패시키지 않는다.

매핑 자체는 DECISIONS 등록 대기 중이다. `docs/AI_TEAM_CONFIRMATION_REQUESTS.md`
3번 항목을 참조한다.

## 게이트 통과 · 위치 임계 미달 처리

게이트(`thr_gate 0.10`, 8개 이상)는 통과했는데 `thr_loc 0.12`를 넘긴 박스가
없으면, 게이트를 통과한 박스 중 최고점 1개를 결함으로 승격한다. 승격하지
않으면 `REJECT`인데 결함 0개인 응답이 나가 BE의 `defect_result` 규약이
깨진다.

## 검증

`tests/test_rgb_owlv2_defect.py`가 정상 응답, 태그 매핑, 구조물 태그 제외,
미지 태그 처리, bbox 변환, 빈 이미지 거부를 검사한다.
`tests/test_rgb_ext_infer_frame.py`가 결함 승격과 `_max_score` 산출을
검사한다. 실제 GPU 회귀 검증은 모델 레포의 `golden_fixture_deploy.json`
20장을 기준으로 별도 수행한다.

## OWLv2 ONNX 변환

판정에 참여하는 OWLv2 검출기만 ONNX로 변환한다. 설명용 Qwen2.5-VL은
현재 판정 경로에 없으므로 변환 대상이 아니다.

```powershell
python -m pip install -r requirements-rgb-defect-onnx.txt
python -m scripts.export_rgb_owlv2_onnx `
  --output models/rgb_owlv2_onnx `
  --device cuda `
  --dtype fp16
```

Optimum ONNX는 모델이 고정한 `transformers==5.14.1`과 호환되지 않으므로
PyTorch의 `torch.onnx.export(dynamo=True)`를 직접 사용한다. 변환기는 모델
ID와 revision을 고정하고, ONNX 및 processor 파일과
`export_metadata.json`을 같은 디렉터리에 저장한다. 운영 코드는
`OnnxExtInspector`를 사용하여 원본 코드와 동일한 크롭, 정사각 패딩,
임계값, 좌표 복원 경로를 유지한다.

변환 후 실제 배포 픽스처로 PyTorch와 ONNX 결과를 비교한다.

```powershell
python -m scripts.validate_rgb_owlv2_onnx `
  --images C:\path\to\rgb-fixtures `
  --model-dir models/rgb_owlv2_onnx
```

통과 기준은 판정·결함 수·유형 완전 일치, bbox 최대 차이 8px 이하,
score 차이 0.002 이하이다. 실제 ONNX 파일은 용량이 크므로 Git에
커밋하지 않는다.

변환과 회귀 검증이 통과한 뒤 서버는 다음처럼 기동한다.

```powershell
docker build -f Dockerfile.rgb-defect-onnx -t ai-infer:rgb-onnx .
docker run --rm --gpus all -p 8000:8000 `
  -e INFERENCE_MODE=rgb-onnx `
  -e RGB_QUALITY_MODEL_PATH=/models/quality_rgb.onnx `
  -e RGB_DEFECT_MODEL_DIR=/models/rgb_owlv2_onnx `
  -v ${PWD}/models:/models:ro `
  ai-infer:rgb-onnx
```

`rgb-onnx` 모드에서는 `/infer/rgb`가 RGB 품질 ONNX와 OWLv2 ONNX를
연속 실행한다. CT 결함 ONNX가 확정되기 전까지 `/infer/ct`는 기존 스텁을
유지한다.

## 현재 검증 결과

- 형식: FP32, opset 18, 고정 배치 1
- 산출물: `model.onnx` + 외부 가중치 `model.onnx.data`
- 외부 가중치 크기: 약 1.62GiB
- `model.onnx` SHA-256:
  `efaebd550d6fe42bdfa5f1647345df48e899d86a76085cfb5fe58567a07464d3`
- `model.onnx.data` SHA-256:
  `88cbf7f916dfc05dfdab0171d0a54e3e50ddbf75f2689d937452a66c29d44656`
- PyTorch exporter 자체 ONNX Runtime 정확도 검증: 통과
- 실제 RGB 결함 이미지 2장 비교: 2/2 통과
- 판정, 결함 수, 유형, bbox, score 모두 완전 일치
- bbox 최대 차이: `0px`
- score 최대 차이: `0.0`
- 실제 `rgb-onnx` 전체 파이프라인 및 `InferResponse` 검증: 통과
- 확인 응답: `REJECT`, 한국어 결함 6개, bbox 계약 변환 정상

22장 전체 및 골든 픽스처 20장 검증은 GPU 환경에서 수행한다. CPU에서는
이미지 한 장의 PyTorch/ONNX 순차 비교에 약 2~3분이 걸린다.
