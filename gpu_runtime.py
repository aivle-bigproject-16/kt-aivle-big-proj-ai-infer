import ctypes
from pathlib import Path

import onnxruntime as ort
import torch
import uvicorn


def preload_cuda_runtime() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available to PyTorch")

    ort.preload_dlls()
    provider_library = next(
        Path(ort.__file__).parent.rglob(
            "libonnxruntime_providers_cuda.so"
        ),
        None,
    )

    if provider_library is None:
        raise RuntimeError(
            "libonnxruntime_providers_cuda.so is missing — the image "
            "installed onnxruntime instead of onnxruntime-gpu"
        )

    ctypes.CDLL(str(provider_library))


if __name__ == "__main__":
    preload_cuda_runtime()
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
