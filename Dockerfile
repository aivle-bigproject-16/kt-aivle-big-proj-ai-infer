FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 1000 \
      --index-url https://download.pytorch.org/whl/cpu \
      torch==2.11.0 torchvision==0.26.0 \
    && pip install --no-cache-dir --timeout 1000 \
      -r requirements.txt

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      libgl1 \
      libglib2.0-0 \
      libxcb1 \
    && rm -rf /var/lib/apt/lists/*

COPY main.py downloader.py adapters.py schemas.py settings.py adapter_factory.py onnx_quality_ct.py onnx_quality_rgb.py ct_defect_onnx.py ./

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
