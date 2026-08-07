# RGB 결함 모델 통합 상태

## 구현 범위

- 모델 레포 `kt-aivle-big-proj-model-rgb`의 커밋 `09563fc`에서
  `ext_infer.py`와 `ext_requirements.lock.txt`를 원본 해시 그대로 가져왔다.
  서버에서는 각각 `rgb_ext_infer.py`,
  `requirements-rgb-defect.lock.txt`로 관리한다.
- 한 장의 이미지 바이트를 OWLv2의 `infer_frames()`에 전달한다.
- 모델의 원본 좌표계 `bbox=[x1,y1,x2,y2]`를 서버 계약의
  `{x,y,width,height}`로 변환한다.
- 모델의 한국어 `유형후보[0]`을 변환하지 않고 `defectType`으로 반환한다.
- 정상 결과는 `PASS`, `confidence=1.0`, `defects=[]`로 반환한다.
- Qwen2.5-VL은 판정에 영향을 주지 않는 설명용 2차 모델이므로 현재 API
  어댑터에는 포함하지 않는다.

## 현재 결함 유형

현재 서버는 RGB 모델이 출력하는 다음 6종을 그대로 반환한다.

- `녹·부식`
- `벗겨짐·박리`
- `파손·찢김`
- `긁힘·스크래치`
- `들뜸`
- `오염·이물질`

기존 SSOT의 RGB 값 `CRACK`, `SPOT`과 다르므로 DB 및 BE 계약을 확인해야
한다. 관련 권고사항은 `DB_RECOMMENDATIONS.md`에 기록한다.

## 검증

`tests/test_rgb_owlv2_defect.py`가 정상 응답, 6종 원본 태그 유지,
bbox 변환, 빈 이미지 거부를 검사한다. 실제 GPU 회귀 검증은 모델 레포의
`golden_fixture_deploy.json` 20장을 기준으로 별도 수행한다.

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
