# v0.2.0 수정 계획서 — 계약 정합 및 운영 결함 정리

작성: 2026-08-10 04:22 (KST)
대상 브랜치: `feat/onnx-inference-server`
직전 상태: `8f95f8e docs: clarify Qwen deployment scope`

---

## 0. 이 문서의 목적과 근거

이 문서는 `kt-aivle-big-proj-ai-infer` 레포 전수 리뷰(2026-08-10)에서 확인된 결함과, 그 각각을 어떻게 고칠지를 기록한다.
수정 근거는 다음 두 가지로 한정한다.

1. **빅프로젝트 SSOT** — 노션 Core(로컬 미러 `AIVLE_Resilio/빅 프로젝트/_notion_mirror/CORE.md`)와 DECISIONS 레지스터.
2. **레포 안의 코드 자체**.

리뷰 시점에 참조한 SSOT 레코드는 아래와 같다.

| 근거 | 상태 | 내용 |
| --- | --- | --- |
| CORE §6.5 / A-5 | ACTIVE | `defectType` 와이어 표기는 영문 4종 고정 — `SWELLING` · `SPOT` · `MICRO_DEFECT` · `CRACK` |
| CORE §12.4 / L-3 | ACTIVE | `defects[].defectType`의 값 집합은 "§6.5 4종이 전부"다 |
| A-4 | ACTIVE | PASS일 때 최상위 `confidence` = `1 − (임계값 미만 최고 결함 점수)`, 후보가 아예 없으면 `1.0` |
| A-1 | ACTIVE | `defects[]`는 배열이며 각 원소는 `{ defectType, confidence, bbox }` |
| CORE §12.1 / B-26 | ACTIVE | `label` enum은 `PASS` · `REJECT` · `FAIL` 3값. `FAIL`은 분류기가 낸 "처리 불가"이며 200으로 정상 반환한다 |
| CORE §12.1 / A-2 | ACTIVE / OPEN | SAHI는 CT만 ON(slice 1280 고정), RGB는 OFF |
| CORE §12.2 | ACTIVE | `AI_TIMEOUT_SECONDS` = 15초. 초과 시 BE가 검사를 `FAIL(TIMEOUT)` 처리한다 |
| L-21 | OPEN | `defectType` 값 집합이 파트 문서마다 갈리는 문제가 이미 등록되어 있다 |

---

## 1. 요약

총 15건을 수정한다. 분류는 다음과 같다.

| 구분 | 건수 | 성격 |
| --- | --- | --- |
| 계약 위반 (C) | 3 | SSOT가 정한 계약을 코드가 어기고 있다 |
| 심각 (S) | 3 | 런타임 크래시 또는 배포 불가 |
| 중간 (M) | 9 | 동작은 하지만 의도와 다르게 동작한다 |

인증 도입(엔드포인트 무인증 문제)은 인프라 파트의 결정 사항이므로 이번 범위에서 제외하고, `docs/AI_TEAM_CONFIRMATION_REQUESTS.md`에 확인 요청으로만 남긴다.

---

## 2. 계약 위반 (C)

### C-1. RGB 결함 유형이 계약에 없는 한글 태그로 나간다

**현상**
`rgb_ext_infer.py`의 OWLv2 파이프라인은 `QUERY_MAP` 키(`녹·부식`, `벗겨짐·박리`, `파손·찢김`, `긁힘·스크래치`, `들뜸`, `오염·이물질`)를 `유형후보`에 담는다.
`rgb_owlv2_defect.py:72`가 그 첫 원소를 그대로 `defectType`에 넣고, `schemas.py`의 `DefectType`이 그 한글 값을 허용하도록 확장되어 있다.

**계약**
CORE §6.5와 §12.4는 `defectType`의 값 집합을 영문 4종으로 못박는다. BE의 `defect_result.defect_type` 컬럼과 vlm 요청 매핑이 모두 이 4종을 전제한다.

**추가 위험**
`DROP_TAGS`(`rgb_ext_infer.py:71`)는 `정상:금속캡`을 의도적으로 남긴다(주석: 구조물로 지우면 진짜 결함 9개를 잃는다). 이 태그가 최고점 후보가 되면 `유형후보`에 `정상:금속캡`이 실려 나가고, 스키마에도 없는 값이라 pydantic 검증 실패로 500이 난다.

**수정**
어댑터 경계에서 한글 태그를 영문 코드로 변환한다. 매핑표는 아래로 확정한다.

| OWLv2 태그 | `defectType` | 근거 |
| --- | --- | --- |
| `파손·찢김` | `CRACK` | 질의어가 `tear in plastic film` · `crack on surface` · `puncture hole` · `dent`로, 갈라짐 계열이다 |
| `긁힘·스크래치` | `CRACK` | 표면 파단 계열로 `CRACK`에 귀속한다 |
| `녹·부식` | `SPOT` | 변색·얼룩 계열로 오점에 귀속한다 |
| `오염·이물질` | `SPOT` | 오염 계열로 오점에 귀속한다 |
| `벗겨짐·박리` | `SWELLING` | 필름이 들뜨며 부풀어 오르는 현상이다 |
| `들뜸` | `SWELLING` | 질의어가 `air bubble under film` · `lifted film edge`로, 부풀음 그 자체다 |
| `정상:금속캡` | (제외) | 결함이 아니라 정상 구조물이다. 결함 배열에서 버린다 |

- `schemas.py`의 `DefectType`은 영문 4종만 남긴다.
- 매핑에 없는 태그가 오면 그 결함 하나만 버리고, 서버 로그에 경고를 남긴다. 요청 전체를 실패시키지 않는다.
- 매핑 결과 결함 배열이 비면 C-3 규칙을 적용한다.
- 이 매핑은 `A-5`의 하위 세부이므로 DECISIONS에 신규 레코드 등록을 요청한다(§6 참조). `SWELLING`을 내는 모델이 없다던 CORE §6.5 서술이 이 매핑으로 바뀌므로, 해당 문장의 개정도 함께 요청한다.

### C-2. PASS일 때 최상위 confidence가 A-4를 따르지 않는다

**현상**
`ct_defect_onnx.py:100-104`와 `rgb_owlv2_defect.py:43-47`이 PASS일 때 무조건 `confidence: 1.0`을 반환한다.

**계약**
A-4는 PASS 시 최상위 confidence를 `1 − (임계값 미만 최고 결함 점수)`로 정의한다. 후보가 아예 없을 때만 `1.0`이다.

**수정**
- CT: 결함 채택 임계값을 `CT_DEFECT_CONF_THRESHOLD` 환경변수로 분리한다(기본 `0.05`, 현재 SAHI 수집 하한과 동일하므로 기본값에서는 동작이 바뀌지 않는다). 임계값 이상인 박스만 `defects[]`에 담고, PASS일 때는 임계값 미만 박스 중 최고 점수를 써서 `1 − score`를 계산한다. 후보가 없으면 `1.0`이다.
- RGB: 게이트가 박스 개수 기준(`n_gate = 8`)이라 A-4의 "임계값 미만 최고 점수" 정의가 그대로 들어맞지 않는다. `rgb_ext_infer.py`의 프레임 결과에 `_max_score`(모든 박스의 최고 점수) 필드를 **추가만** 하고, 어댑터가 PASS일 때 `1 − _max_score`를 쓴다. 박스가 하나도 없으면 `1.0`이다. `_max_score`는 판정 로직에 관여하지 않는 순수 추가 필드이므로 기존 회귀 픽스처(`verify_fixture`)에 영향이 없다.
- A-4가 개수 게이트 모델을 상정하지 않았다는 점은 확인 요청으로 남긴다(§6).

### C-3. RGB가 `REJECT`이면서 결함 0개를 반환할 수 있다

**현상**
`rgb_ext_infer.py:368`의 게이트는 `thr_gate = 0.10` 이상인 박스가 8개 이상이면 `판정 = 결함`이다.
그런데 `결함` 배열은 `thr_loc = 0.12` 이상만 담는다(`:384`). 두 임계 사이(0.10 ~ 0.12)의 박스만 8개 이상이면 판정은 결함인데 결함 배열은 빈다.
그 결과 `rgb_owlv2_defect.py:57`의 `default=0.0`이 발동해 `label = REJECT`, `confidence = 0.0`, `defects = []`가 나간다.

**계약**
CORE §6.4·§8은 REJECT 검사가 결함 수만큼 `defect_result` N행을 갖는다고 규정한다. 결함 0개인 REJECT는 DB에 아무 행도 남기지 못해 결함 통계에서 사라진다.

**수정**
`_frame_result`에서 결함 채택 대상이 비었을 때, 게이트를 통과한 박스(`>= thr_gate`) 중 최고 점수 1개를 결함으로 승격한다.
게이트가 결함이라 판정했다면 위치 근거가 최소 하나는 있어야 계약이 성립하고, 그 박스는 실제로 게이트 임계를 넘긴 박스이므로 근거 없는 값이 아니다.
판정 로직(`n_gate` 계산과 `flag`)은 한 글자도 건드리지 않는다. 이 승격 규칙도 확인 요청으로 등록한다(§6).

---

## 3. 심각 (S)

### S-1. CPU `Dockerfile`이 RGB 소스를 담지 않는다

`Dockerfile:20`의 `COPY`에 `rgb_ext_infer.py` · `rgb_ext_infer_onnx.py` · `rgb_owlv2_defect.py`가 빠져 있다. `requirements.txt`에는 `transformers`도 없다.
그런데 `settings.py`는 그 이미지에서도 `rgb-onnx` · `onnx` 모드를 허용하므로, 해당 모드로 뜨면 부팅 즉시 `ImportError`로 죽는다. GHCR에 발행되는 이미지가 바로 이 이미지다.

**수정**
- `COPY`를 `COPY *.py ./`로 바꿔 소스 누락이 구조적으로 재발하지 않게 한다.
- CPU 이미지에는 `transformers` 스택을 넣지 않는다. RGB 실모델 경로는 GPU 이미지(`Dockerfile.gpu-onnx`) 담당이다.
- RGB 어댑터 생성 시 의존성이 없으면 어떤 이미지를 써야 하는지 알려주는 `RuntimeError`를 던진다.
- README에 이미지별 지원 모드 표를 추가한다.

### S-2. 어댑터를 import 시점에 만든다

`main.py:18-19`가 모듈 최상위에서 두 어댑터를 만든다. 모델 파일이 없거나 세션 생성이 실패하면 uvicorn이 스택트레이스와 함께 죽고 `/health`조차 뜨지 않는다.

**수정**
어댑터 생성을 `try` / `except`로 감싸 실패를 저장한다. 서버는 계속 뜨고, `/health`가 실패 사유를 보고하며, 해당 모달 추론 요청은 503으로 답한다.
테스트가 `main.CT_ADAPTER` · `main.RGB_ADAPTER`를 직접 monkeypatch하므로 모듈 속성 이름은 유지한다.

### S-3. 어댑터 예외가 그대로 500으로 나간다

`main.py:39`의 `adapter.predict()`에 예외 처리가 없다. 전처리 단계의 `ValueError("invalid CT image")`는 클라이언트가 잘못된 이미지를 준 경우인데도 500으로 나간다.

**수정**
- `ValueError` → 422 (`unprocessable inference image`)
- 그 외 예외 → 500 (`inference failed`)
- 어댑터 미준비 → 503

`FAIL`은 예외가 아니라 분류기가 내는 정상 200 응답이라는 점(B-26)은 그대로 유지한다.

---

## 4. 중간 (M)

| ID | 위치 | 문제 | 수정 |
| --- | --- | --- | --- |
| M-1 | `adapter_factory.py:87-91` | `"rgb-onnx"` 분기가 도달 불가능한 죽은 코드다 | 모드 → (모달별 어댑터) 형태의 단일 디스패치 표로 재작성한다 |
| M-2 | `adapter_factory.py:93,97` | `providers=`를 안 넘겨 `ONNX_DEVICE=cuda`인데도 조용히 CPU로 돈다 | 모든 ONNX 어댑터 생성에 `providers`를 넘긴다 |
| M-3 | `main.py:67` | `/health`가 `models: {ct: true, rgb: true}`를 하드코딩한다 | 모달별 실제 어댑터 종류와 준비 여부를 보고한다. 하나라도 실패면 `status: "degraded"` |
| M-4 | `downloader.py:22-26` | 사설·루프백·링크로컬 IP를 막지 않는다 (SSRF) | 호스트를 해석해 사설 대역이면 거부한다. 해석 실패 시에는 기존 경로대로 httpx가 처리하게 둔다 |
| M-5 | `.gitignore:7` | `htmlcov/`와 `models/*.onnx`가 한 줄로 붙어 둘 다 무효다 | 두 줄로 분리하고 `models/` 전체를 무시한다 |
| M-6 | `.dockerignore` | `models/`가 없어 빌드 컨텍스트에 1.7GB 가중치가 딸려간다 | `models/`, `docs/`, `scripts/`를 추가한다 |
| M-7 | `onnx_quality_ct.py:14`, `onnx_quality_rgb.py:10` | 판정 임계값이 코드에 하드코딩되어 있다 | `CT_QUALITY_THRESHOLD` · `RGB_QUALITY_FAIL_THRESHOLD`로 `settings.py`에 이관한다 (기본값은 현행 유지) |
| M-8 | `onnx_quality_rgb.py:73` | 출력 채널 순서(0=FAIL, 1=PASS) 가정에 근거가 없다 | 근거 주석을 달고 순서를 검증하는 테스트를 추가한다 |
| M-9 | `gpu_runtime.py:15` | 프로바이더 라이브러리를 못 찾으면 `StopIteration`이 난다 | 원인을 알려주는 `RuntimeError`로 바꾼다 |
| M-10 | `README.md:3,35` | "스텁 어댑터만 제공"이라는 서술이 현재 상태와 다르다 | 모드·이미지·환경변수 표로 갱신한다 |
| M-11 | `.github/workflows/ci.yml:28` | `ultralytics` 때문에 CUDA torch(약 2.5GB)를 받아 CI가 느리다 | CPU 전용 인덱스로 torch를 먼저 설치한다 |
| M-12 | `Dockerfile:12` | apt 설치가 pip 뒤라 레이어 캐시가 매번 깨진다 | apt를 pip 앞으로 옮긴다 |

---

## 5. 테스트 계획

기존 테스트 중 다음 두 개는 계약이 바뀌었으므로 교체한다.

- `tests/test_contract.py::test_rgb_model_defect_types_are_accepted_by_response_schema` — 한글 6종이 스키마에 통과하는지 확인하던 테스트다. 영문 4종만 통과하고 한글은 거부되는지 확인하도록 바꾼다.
- `tests/test_rgb_owlv2_defect.py::test_model_defect_types_are_returned_without_mapping` — 매핑 없이 한글을 그대로 내보내는지 확인하던 테스트다. 매핑표대로 변환되는지 확인하도록 바꾼다.

신규 테스트는 다음과 같다.

| 대상 | 확인 내용 |
| --- | --- |
| C-1 | 한글 6종이 영문 4종으로 변환된다 / `정상:금속캡`이 결함에서 빠진다 / 미지의 태그가 와도 500이 아니다 |
| C-2 | CT PASS 시 `confidence == 1 − 임계 미만 최고 점수` / 후보 없으면 `1.0` / RGB도 동일 |
| C-3 | 게이트는 통과했는데 `thr_loc` 이상 박스가 없을 때 결함 1개가 승격된다 |
| S-2 | 어댑터 생성 실패 시 `/health`가 `degraded`를 보고하고 추론이 503을 준다 |
| S-3 | 어댑터가 `ValueError`를 던지면 422가 나온다 |
| M-2 | `ct-quality-onnx` · `quality-onnx` 모드에서도 CUDA 프로바이더가 전달된다 |
| M-4 | 루프백·사설·링크로컬 호스트가 거부된다 |

---

## 6. SSOT에 등록을 요청할 항목

아래 3건은 이 레포에서 임의로 정할 수 없는 계약 사항이다. `docs/AI_TEAM_CONFIRMATION_REQUESTS.md`에 적고 DECISIONS 등록을 요청한다.

1. **RGB OWLv2 태그 → 영문 4종 매핑표** (§2 C-1). A-5의 하위 세부이며, 채택되면 CORE §6.5의 "`SWELLING`을 내보내는 모델은 현재 없다"는 서술이 더 이상 참이 아니다. RGB 모델이 CORE 서술(`CRACK`(Damaged) · `SPOT`(Pollution) 2종 분류기)에서 OWLv2 제로샷 6종으로 바뀐 사실 자체도 Core에 반영되어야 한다.
2. **개수 게이트 모델에서의 A-4 적용 방식** (§2 C-2). A-4는 점수 임계 모델을 전제로 쓰였다.
3. **게이트 통과 · 위치 임계 미달일 때의 결함 승격 규칙** (§2 C-3). REJECT의 `defect_result` 행 수 규약(C-7과 인접)에 영향을 준다.

L-21(OPEN)은 이 레포의 한글 태그 문제와 같은 뿌리이므로, C-1을 처리한 뒤 해당 레코드에 이 레포 조치 내역을 덧붙이도록 담당자에게 요청한다.

---

## 7. 작업 순서

1. 계획서 커밋 (이 문서)
2. C-1 — 매핑표 · 스키마 · 테스트
3. C-2 — A-4 confidence (CT · RGB)
4. C-3 — RGB 결함 승격
5. S-1 — Dockerfile · 이미지 지원 모드
6. S-2 · S-3 — 기동 내성 · 예외 → HTTP 코드
7. M-1 · M-2 · M-7 — 팩토리 재작성과 설정 이관
8. M-3 — `/health`
9. M-4 — SSRF 방어
10. M-5 · M-6 · M-9 · M-11 · M-12 — 빌드 · 무시 파일 · 런타임 정리
11. M-10 — README
12. 확인 요청 문서 갱신 후 푸시

각 단계를 개별 커밋으로 쪼갠다. 커밋 메시지에 AI 푸터는 넣지 않는다.

---

## 8. 범위 밖

| 항목 | 이유 |
| --- | --- |
| `/infer/*` 인증 | 인프라 파트 결정 사항이다. 확인 요청으로만 남긴다 |
| 동시 요청 제한(세마포어) | A-2(장당 추론시간 실측)가 OPEN이라 적정 동시성을 정할 근거가 없다 |
| `latency_ms`의 의미 | Core에 정의가 없다. 현행(다운로드 포함 요청 처리 전체)을 유지하고 README에 명시만 한다 |
| `SWELLING` 사용 여부 | C-1 매핑이 채택되면 자연히 해소된다 |
