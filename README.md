# kt-aivle-big-proj-ai-infer

KT AIVLE 빅프로젝트 16조 AI 추론 서버입니다. 현재는 실제 모델 대신 계약과 배포 경로를 검증하는 스텁 어댑터를 제공합니다.

## API

- `POST /infer/ct`: CT 이미지 추론 (`MICRO_DEFECT`)
- `POST /infer/rgb`: RGB 이미지 추론 (`CRACK`, `SPOT`)
- `GET /health`: 서버 준비 상태

요청의 `image_url`은 BE가 발급한 presigned URL이며, 서버가 이미지를 직접 다운로드합니다.

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

실제 CT/RGB 모델 파일이 준비되면 `InferenceAdapter` 구현을 교체합니다.
