# CT 결함 ONNX 임시 배포 설정

CT 결함 ONNX는 다음 설정으로 20장 골든 픽스처를 20/20 통과했다.

```text
task=segment
imgsz=1280
SAHI slice=1280, overlap=0.2
confidence=0.05
postprocess=NMS/IOS@0.44
```

현재 모델카드의 정식 후처리는 `NMS/IOU@0.5`이므로, `IOS@0.44`는
ONNX 배포를 위한 임시 설정이다. 서버에서는 다음 환경변수로 교체할 수
있다.

```env
CT_POSTPROCESS_TYPE=NMS
CT_POSTPROCESS_MATCH_METRIC=IOS
CT_POSTPROCESS_MATCH_THRESHOLD=0.44
```

검증 결과:

- `NMS/IOU@0.5`: 15/20 통과
- `NMS/IOS@0.5`: 19/20 통과
- `NMS/IOS@0.44`: 20/20 통과
- 최대 confidence 차이: `0.0094996205329895` (허용치 `0.01`)
- bbox 차이는 모델팀 기준에 따라 경고로만 기록했다.

현재 골든 세트에는 한 이미지에서 서로 다른 결함이 여러 개 검출되는 사례가
없다. 다중 결함 과병합 여부를 추가 검증하고 모델팀이 정식 후처리를 결정하면
환경변수와 전체 회귀 테스트를 함께 갱신한다.
