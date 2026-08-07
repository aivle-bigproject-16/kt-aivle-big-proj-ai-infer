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
