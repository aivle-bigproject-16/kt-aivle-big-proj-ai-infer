$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$image = "kt-aivle-big-proj-ai-infer:gpu-onnx-local"

Set-Location $repo

Write-Host "`n=== Build unified GPU ONNX image ===" -ForegroundColor Cyan
docker build `
    --file Dockerfile.gpu-onnx `
    --tag $image `
    .

if ($LASTEXITCODE -ne 0) {
    throw "GPU image build failed."
}

Write-Host "`n=== Inspect image ===" -ForegroundColor Cyan
docker image inspect $image --format "ID={{.Id}} Size={{.Size}}"

if ($LASTEXITCODE -ne 0) {
    throw "Built GPU image was not found."
}

Write-Host "`n=== Validate GPU runtime packages ===" -ForegroundColor Cyan
docker run --rm `
    --entrypoint python `
    $image `
    -c "import torch, torchvision, onnxruntime as ort, cv2, sahi, transformers; print('Torch:', torch.__version__); print('Torchvision:', torchvision.__version__); print('CUDA build:', torch.version.cuda); print('GPU attached:', torch.cuda.is_available()); print('ORT providers:', ort.get_available_providers()); print('OpenCV:', cv2.__version__); print('SAHI: PASS'); print('Transformers:', transformers.__version__); assert 'CUDAExecutionProvider' in ort.get_available_providers()"

if ($LASTEXITCODE -ne 0) {
    throw "GPU runtime validation failed."
}

Write-Host "`n=== Validate CUDA provider library preload ===" `
    -ForegroundColor Cyan

docker run --rm `
    --entrypoint python `
    $image `
    -c "import ctypes, pathlib, torch, onnxruntime as ort; ort.preload_dlls(); provider = next(pathlib.Path(ort.__file__).parent.rglob('libonnxruntime_providers_cuda.so')); ctypes.CDLL(str(provider)); print('CUDA provider library preload: PASS')"

if ($LASTEXITCODE -ne 0) {
    throw "CUDA provider library preload validation failed."
}

Write-Host "`nUnified GPU ONNX image validation passed." -ForegroundColor Green
