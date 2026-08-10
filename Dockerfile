FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      libgl1 \
      libglib2.0-0 \
      libxcb1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 1000 \
      --index-url https://download.pytorch.org/whl/cpu \
      torch==2.11.0 torchvision==0.26.0 \
    && pip install --no-cache-dir --timeout 1000 \
      -r requirements.txt

# 소스는 통째로 넣는다. 파일 단위로 나열하면 RGB 모듈이 빠진 채 발행되는
# 사고가 재발한다. 이 이미지는 stub 과 CT ONNX 모드만 지원한다 —
# RGB 실모델(transformers 의존)은 Dockerfile.gpu-onnx 담당이다.
COPY *.py ./

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
