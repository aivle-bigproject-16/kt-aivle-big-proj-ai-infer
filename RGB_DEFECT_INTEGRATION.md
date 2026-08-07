# RGB 결함 모델 통합 상태

## 구현 범위

- 모델 레포 `kt-aivle-big-proj-model-rgb`의 커밋 `09563fc`에서
  `ext_infer.py`와 `ext_requirements.lock.txt`를 원본 해시 그대로 가져왔다.
  서버에서는 각각 `rgb_ext_infer.py`,
  `requirements-rgb-defect.lock.txt`로 관리한다.
- 한 장의 이미지 바이트를 OWLv2의 `infer_frames()`에 전달한다.
- 모델의 원본 좌표계 `bbox=[x1,y1,x2,y2]`를 서버 계약의
  `{x,y,width,height}`로 변환한다.
- 정상 결과는 `PASS`, `confidence=1.0`, `defects=[]`로 반환한다.
- Qwen2.5-VL은 판정에 영향을 주지 않는 설명용 2차 모델이므로 현재 API
  어댑터에는 포함하지 않는다.

## 활성화 차단 사유

모델은 다음과 같은 한국어 후보 태그를 반환하지만 서버 계약은
`CRACK`, `SPOT`만 허용한다. 승인된 대응표가 아직 없으므로 어댑터에는
기본 매핑을 두지 않았다. 결함 응답에 매핑이 없으면
`RgbDefectTypeMappingRequired`를 발생시켜 잘못된 저장을 막는다.

따라서 다음 매핑이 확정되기 전에는 `adapter_factory.py`의 운영 모드에
연결하지 않는다.

```text
모델의 한국어 유형후보 -> CRACK 또는 SPOT
```

## 검증

`tests/test_rgb_owlv2_defect.py`가 정상 응답, 매핑 누락 차단, 결함 변환,
빈 이미지 거부를 검사한다. 실제 GPU 회귀 검증은 모델 레포의
`golden_fixture_deploy.json` 20장을 기준으로 별도 수행한다.
