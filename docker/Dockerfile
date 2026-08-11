# CPU 이미지 — stub 과 CT ONNX 모드 전용.
# RGB 실모델(transformers 의존)은 Dockerfile.gpu-onnx 담당이다.
# 빌드 컨텍스트는 리포지토리 루트다: docker build -f docker/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      libgl1 \
      libglib2.0-0 \
      libxcb1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt ./requirements/base.txt
RUN pip install --no-cache-dir --timeout 1000 \
      --index-url https://download.pytorch.org/whl/cpu \
      torch==2.11.0 torchvision==0.26.0 \
    && pip install --no-cache-dir --timeout 1000 \
      -r requirements/base.txt

# 패키지를 통째로 넣는다. 모듈 단위로 나열하면 RGB 모듈이 빠진 채 발행되는
# 사고가 재발한다.
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
