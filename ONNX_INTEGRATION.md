# 통합 ONNX 실행 모드

`INFERENCE_MODE=onnx`는 네 모델을 한 FastAPI 서버에 연결한다.

| 엔드포인트 | 품질 모델 | 결함 모델 |
|---|---|---|
| `/infer/ct` | `quality_ct.onnx` | `defect_ct.onnx` |
| `/infer/rgb` | `quality_rgb.onnx` | `rgb_owlv2_onnx/` |

모델은 이미지에 포함하거나 Git에 커밋하지 않고 `/models`에 읽기 전용으로
마운트한다. 로컬 통합 이미지는 `Dockerfile.onnx`로 빌드한다.

```bash
docker build -f Dockerfile.onnx -t ai-infer:onnx-local .
```

CT 결함 후처리 기본값은 검증된 임시 설정 `NMS/IOS@0.44`다. 모델카드의
정식 설정 `NMS/IOU@0.5`와 다르며, 환경변수와 회귀검증을 통해 교체할 수
있다.
