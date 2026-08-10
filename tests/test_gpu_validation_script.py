from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path("scripts/run-gpu-validation.ps1")
UPLOAD_SCRIPT = Path("scripts/upload-gpu-validation-fixtures.ps1")
GPU_RUNTIME = Path("gpu_runtime.py")
GPU_DOCKERFILE = Path("Dockerfile.gpu-onnx")


def test_gpu_validation_script_has_cost_and_target_guards():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "[switch]$Execute" in text
    assert "if (-not $Execute)" in text
    assert 'expectedName = "ai-infer-gpu-validation"' in text
    assert 'expectedType = "g6e.xlarge"' in text
    assert "PingStatus" in text
    assert "CtFixtureKey" in text
    assert "RgbFixtureKey" in text
    assert "CtImageUrl" not in text
    assert "RgbImageUrl" not in text
    assert "aws s3 presign" in text
    assert "AllowRgbSmokeOnly" in text


def test_gpu_validation_script_checks_gpu_models_and_both_apis():
    text = SCRIPT.read_text(encoding="utf-8")

    required_fragments = (
        "nvidia-smi",
        "docker run --rm -i --gpus all",
        "sha256",
        "ONNX_DEVICE=cuda",
        "CUDAExecutionProvider",
        "/infer/ct",
        "/infer/rgb",
        "model-manifest.json",
        "onnx-20260809-01",
        "onnx-cuda12-ort126",
    )

    for fragment in required_fragments:
        assert fragment in text

    assert "aws ssm wait command-executed" not in text
    assert "for ($attempt = 1; $attempt -le 360" in text
    assert "if not key.startswith(prefix):" in text
    assert 'if relative_path.is_absolute() or ".." in relative_path.parts' in text
    assert 'response["label"] == "REJECT"' in text
    assert 'assert response["defects"]' in text
    assert "RGB validation level: SMOKE ONLY" in text
    assert "PYTHONIOENCODING=utf-8" in text
    assert "[Console]::OutputEncoding" in text
    assert '$env:PYTHONUTF8 = "1"' in text
    assert '$env:AWS_CLI_FILE_ENCODING = "UTF-8"' in text
    assert "=== Direct CT GPU probe ===" in text
    assert "CT quality session providers:" in text
    assert text.count("ort.preload_dlls()") >= 2
    assert "=== Inference container logs ===" in text
    assert 'CT API failed: curl=$ct_curl_exit http=$ct_http_status' in text


def test_gpu_validation_script_dry_run_does_not_require_aws():
    powershell = shutil.which("pwsh") or shutil.which("powershell.exe")
    if not powershell:
        pytest.skip("PowerShell is not available")

    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "DRY RUN: no SSM command was sent." in completed.stdout


def test_fixture_upload_is_guarded_and_verifies_remote_object():
    text = UPLOAD_SCRIPT.read_text(encoding="utf-8")

    assert "[switch]$Execute" in text
    assert "if (-not $Execute)" in text
    assert "DRY RUN: no fixture was uploaded." in text
    assert "Get-FileHash" in text
    assert "head-object" in text
    assert "ContentLength" in text
    assert "Metadata.sha256" in text
    assert "ChecksumSHA256" in text
    assert "--checksum-algorithm SHA256" in text
    assert 'Encryption -ne "AES256"' in text


def test_gpu_runtime_preloads_cuda_libraries_before_app_import():
    runtime = GPU_RUNTIME.read_text(encoding="utf-8")
    dockerfile = GPU_DOCKERFILE.read_text(encoding="utf-8")

    assert "import torch" in runtime
    assert "ort.preload_dlls()" in runtime
    assert "ctypes.CDLL" in runtime
    assert 'uvicorn.run("main:app"' in runtime
    assert "COPY *.py ./" in dockerfile
    assert 'CMD ["python", "gpu_runtime.py"]' in dockerfile
