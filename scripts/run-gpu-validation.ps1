param(
    [switch]$Execute,
    [string]$InstanceId = "",
    [string]$CtFixtureKey = "",
    [string]$RgbFixtureKey = "",
    [string]$CtFixtureSha256 = "",
    [string]$RgbFixtureSha256 = "",
    [switch]$AllowRgbSmokeOnly,
    [string]$Profile = "default",
    [string]$Region = "ap-northeast-2"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$expectedName = "ai-infer-gpu-validation"
$expectedType = "g6e.xlarge"
$stateFile = Join-Path $PSScriptRoot ".gpu-validation-instance-id"
$fixtureStateFile = Join-Path $PSScriptRoot ".gpu-validation-fixtures.json"
$reportFile = Join-Path $PSScriptRoot ".gpu-validation-command-id"
$bucket = "kt-aivle-big-proj-kks"
$bundle = "onnx-20260809-01"
$accountId = "825555019742"
$repository = "kt-aivle-big-proj-ai-infer"
$imageTag = "onnx-ff1eccd"
$image = "${accountId}.dkr.ecr.${Region}.amazonaws.com/${repository}:${imageTag}"

if ($Region -ne "ap-northeast-2") {
    throw "GPU validation is pinned to ap-northeast-2."
}

if (-not $InstanceId -and (Test-Path -LiteralPath $stateFile)) {
    $InstanceId = (Get-Content -LiteralPath $stateFile -Raw).Trim()
}

if (Test-Path -LiteralPath $fixtureStateFile) {
    $fixtureState = Get-Content -LiteralPath $fixtureStateFile -Raw | ConvertFrom-Json
    if (-not $CtFixtureKey) { $CtFixtureKey = $fixtureState.CTFixtureKey }
    if (-not $RgbFixtureKey) { $RgbFixtureKey = $fixtureState.RGBFixtureKey }
    if (-not $CtFixtureSha256) { $CtFixtureSha256 = $fixtureState.CTFixtureSha256 }
    if (-not $RgbFixtureSha256) { $RgbFixtureSha256 = $fixtureState.RGBFixtureSha256 }
}

Write-Host ""
Write-Host "GPU validation plan" -ForegroundColor Cyan
Write-Host "Instance:     $InstanceId"
Write-Host "Model bundle: s3://$bucket/models/ai-infer/$bundle/"
Write-Host "Image:        $image"
Write-Host "CT endpoint:  POST /infer/ct"
Write-Host "RGB endpoint: POST /infer/rgb"

if (-not $Execute) {
    Write-Host ""
    Write-Host "DRY RUN: no SSM command was sent." -ForegroundColor Yellow
    Write-Host "Upload the two fixtures, then use -Execute during paid validation."
    exit 0
}

if ($InstanceId -notmatch "^i-[0-9a-f]+$") {
    throw "A valid validation instance ID is required."
}

if (-not $CtFixtureKey -or -not $RgbFixtureKey -or -not $CtFixtureSha256 -or -not $RgbFixtureSha256) {
    throw "Fixture keys and SHA-256 values are required. Run upload-gpu-validation-fixtures.ps1 first."
}

$fixturePrefix = "models/ai-infer/$bundle/fixtures/"
foreach ($key in @($CtFixtureKey, $RgbFixtureKey)) {
    if (-not $key.StartsWith($fixturePrefix) -or $key.Contains("..")) {
        throw "Fixture keys must stay under $fixturePrefix"
    }
}

foreach ($hash in @($CtFixtureSha256, $RgbFixtureSha256)) {
    if ($hash -notmatch "^[0-9a-f]{64}$") {
        throw "Invalid fixture SHA-256: $hash"
    }
}

$instance = aws ec2 describe-instances `
    --profile $Profile `
    --region $Region `
    --instance-ids $InstanceId `
    --query "Reservations[0].Instances[0].{State:State.Name,Type:InstanceType,Name:Tags[?Key=='Name']|[0].Value}" `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0 -or -not $instance) {
    throw "Validation instance lookup failed."
}

if ($instance.State -ne "running") {
    throw "Validation instance is not running: $($instance.State)"
}

if ($instance.Name -ne $expectedName -or $instance.Type -ne $expectedType) {
    throw "Instance safety check failed."
}

$pingStatus = aws ssm describe-instance-information `
    --profile $Profile `
    --region $Region `
    --filters "Key=InstanceIds,Values=$InstanceId" `
    --query "InstanceInformationList[0].PingStatus" `
    --output text

if ($LASTEXITCODE -ne 0 -or $pingStatus -ne "Online") {
    throw "SSM is not online for $InstanceId."
}

$ctKeyBase64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($CtFixtureKey)
)
$rgbKeyBase64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($RgbFixtureKey)
)
$ctHashBase64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($CtFixtureSha256)
)
$rgbHashBase64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($RgbFixtureSha256)
)
$rgbModeBase64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes(
        $(if ($AllowRgbSmokeOnly) { "smoke" } else { "golden" })
    )
)

$remoteScript = @'
set -euo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONIOENCODING=utf-8

CT_KEY="$(printf '%s' "$1" | base64 -d)"
RGB_KEY="$(printf '%s' "$2" | base64 -d)"
CT_SHA256="$(printf '%s' "$3" | base64 -d)"
RGB_SHA256="$(printf '%s' "$4" | base64 -d)"
RGB_MODE="$(printf '%s' "$5" | base64 -d)"
REGION="ap-northeast-2"
BUCKET="kt-aivle-big-proj-kks"
BUNDLE="onnx-20260809-01"
MODEL_DIR="/opt/ai-infer/models"
IMAGE="825555019742.dkr.ecr.ap-northeast-2.amazonaws.com/kt-aivle-big-proj-ai-infer:onnx-ff1eccd"
CONTAINER="ai-infer-gpu-validation"
FIXTURE_DIR="/opt/ai-infer/fixtures"

echo "=== GPU ==="
nvidia-smi

echo "=== Download model bundle ==="
sudo rm -rf "$MODEL_DIR"
sudo mkdir -p "$MODEL_DIR"
sudo chown "$(id -u):$(id -g)" "$MODEL_DIR"
aws s3 cp "s3://${BUCKET}/models/ai-infer/${BUNDLE}/" "$MODEL_DIR/" --recursive --exclude "fixtures/*" --region "$REGION" >/tmp/model-download.log

echo "=== Verify model bundle ==="
MODEL_DIR="$MODEL_DIR" python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["MODEL_DIR"])
manifest = json.loads((root / "model-manifest.json").read_text())
prefix = manifest["s3Prefix"].rstrip("/") + "/"

for artifact in manifest["artifacts"]:
    key = artifact["s3Key"]
    if not key.startswith(prefix):
        raise RuntimeError(f"key outside manifest prefix: {key}")
    relative_path = Path(key[len(prefix):])
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise RuntimeError(f"unsafe artifact path: {relative_path}")
    path = (root / relative_path).resolve()
    if root.resolve() not in path.parents:
        raise RuntimeError(f"artifact escaped model directory: {path}")
    if path.stat().st_size != artifact["sizeBytes"]:
        raise RuntimeError(f"size mismatch: {relative_path}")
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if digest != artifact["sha256"]:
        raise RuntimeError(f"sha256 mismatch: {relative_path}")
print(f"Model artifact verification: PASS ({len(manifest['artifacts'])} files)")
PY

echo "=== Pull GPU runtime image ==="
aws ecr get-login-password --region "$REGION" | sudo docker login --username AWS --password-stdin "825555019742.dkr.ecr.${REGION}.amazonaws.com"
sudo docker pull "$IMAGE"

echo "=== Validate image GPU providers ==="
sudo docker run --rm -i --gpus all "$IMAGE" python - <<'PY'
import onnxruntime as ort
import torch

assert torch.cuda.is_available(), "PyTorch cannot access CUDA"
providers = ort.get_available_providers()
assert "CUDAExecutionProvider" in providers, providers
print("GPU:", torch.cuda.get_device_name(0))
print("ORT providers:", providers)
PY

echo "=== Download and verify API fixtures ==="
sudo rm -rf "$FIXTURE_DIR"
sudo mkdir -p "$FIXTURE_DIR"
sudo chown "$(id -u):$(id -g)" "$FIXTURE_DIR"
aws s3 cp "s3://${BUCKET}/${CT_KEY}" "$FIXTURE_DIR/ct-image" --region "$REGION"
aws s3 cp "s3://${BUCKET}/${RGB_KEY}" "$FIXTURE_DIR/rgb-image" --region "$REGION"
printf '%s  %s\n' "$CT_SHA256" "$FIXTURE_DIR/ct-image" | sha256sum -c -
printf '%s  %s\n' "$RGB_SHA256" "$FIXTURE_DIR/rgb-image" | sha256sum -c -

CT_URL="$(aws s3 presign "s3://${BUCKET}/${CT_KEY}" --region "$REGION" --expires-in 3600)"
RGB_URL="$(aws s3 presign "s3://${BUCKET}/${RGB_KEY}" --region "$REGION" --expires-in 3600)"

echo "=== Start inference API ==="
sudo docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
sudo docker run -d \
  --name "$CONTAINER" \
  --gpus all \
  --restart no \
  -p 127.0.0.1:8000:8000 \
  -v "$MODEL_DIR:/models:ro" \
  -e INFERENCE_MODE=onnx \
  -e ONNX_DEVICE=cuda \
  -e CT_POSTPROCESS_TYPE=NMS \
  -e CT_POSTPROCESS_MATCH_METRIC=IOS \
  -e CT_POSTPROCESS_MATCH_THRESHOLD=0.44 \
  "$IMAGE"

ready=0
for attempt in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8000/health >/tmp/health.json; then
    ready=1
    break
  fi
  sleep 10
done

if [ "$ready" -ne 1 ]; then
  sudo docker logs "$CONTAINER"
  exit 1
fi

cat /tmp/health.json

export CT_URL RGB_URL RGB_MODE
python3 - <<'PY'
import json
import os
from pathlib import Path

Path("/tmp/ct-request.json").write_text(json.dumps({
    "inspection_id": 3001,
    "image_key": "validation/ct.jpg",
    "image_url": os.environ["CT_URL"],
}))
Path("/tmp/rgb-request.json").write_text(json.dumps({
    "inspection_id": 3002,
    "image_key": "validation/rgb.jpg",
    "image_url": os.environ["RGB_URL"],
}))
PY

echo "=== CT API ==="
curl -fsS -X POST http://127.0.0.1:8000/infer/ct \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/ct-request.json > /tmp/ct-response.json
cat /tmp/ct-response.json

echo "=== RGB API ==="
curl -fsS -X POST http://127.0.0.1:8000/infer/rgb \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/rgb-request.json > /tmp/rgb-response.json
cat /tmp/rgb-response.json

python3 - <<'PY'
import json
import os
from pathlib import Path

for name in ("ct", "rgb"):
    response = json.loads(Path(f"/tmp/{name}-response.json").read_text())
    assert set(response) == {
        "inspection_id", "label", "confidence", "defects", "latency_ms"
    }
    assert isinstance(response["inspection_id"], int)
    assert response["label"] in {"PASS", "REJECT", "FAIL"}
    assert isinstance(response["confidence"], (int, float))
    assert isinstance(response["defects"], list)
    assert isinstance(response["latency_ms"], int)
    if name == "ct" or os.environ["RGB_MODE"] == "golden":
        assert response["label"] == "REJECT", f"{name} defect model was not exercised"
        assert response["defects"], f"{name} returned no defects"
    else:
        assert response["label"] in {"PASS", "REJECT"}, "RGB quality stage returned FAIL"
        if response["label"] == "REJECT":
            assert response["defects"], "RGB REJECT returned no defects"
    for defect in response["defects"]:
        assert set(defect) == {"defectType", "confidence", "bbox"}
        assert isinstance(defect["defectType"], str)
        assert isinstance(defect["confidence"], (int, float))
        assert set(defect["bbox"]) == {"x", "y", "width", "height"}
        assert all(
            isinstance(value, (int, float))
            for value in defect["bbox"].values()
        )
print("CT golden and RGB API validation: PASS")
if os.environ["RGB_MODE"] == "smoke":
    print("RGB validation level: SMOKE ONLY (golden fixture pending)")
PY

echo "=== Recent server logs ==="
sudo docker logs --tail 100 "$CONTAINER"
echo "GPU ONNX validation: PASS"
'@

$scriptBase64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($remoteScript)
)
$remoteCommand = "echo $scriptBase64 | base64 -d > /tmp/run-gpu-validation.sh && chmod 700 /tmp/run-gpu-validation.sh && sudo bash /tmp/run-gpu-validation.sh '$ctKeyBase64' '$rgbKeyBase64' '$ctHashBase64' '$rgbHashBase64' '$rgbModeBase64'"

$parametersFile = Join-Path $env:TEMP "gpu-validation-ssm-parameters.json"
$parameters = @{ commands = @($remoteCommand) } | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText(
    $parametersFile,
    $parameters,
    [Text.UTF8Encoding]::new($false)
)
$parametersUri = "file://" + $parametersFile.Replace("\", "/")

$commandId = aws ssm send-command `
    --profile $Profile `
    --region $Region `
    --instance-ids $InstanceId `
    --document-name "AWS-RunShellScript" `
    --comment "AI inference GPU ONNX validation" `
    --timeout-seconds 3600 `
    --parameters $parametersUri `
    --query "Command.CommandId" `
    --output text

Remove-Item -LiteralPath $parametersFile -Force

if ($LASTEXITCODE -ne 0 -or -not $commandId) {
    throw "Failed to send the GPU validation command."
}

[IO.File]::WriteAllText(
    $reportFile,
    $commandId.Trim(),
    [Text.UTF8Encoding]::new($false)
)

Write-Host "SSM command: $commandId"
Write-Host "Waiting for validation completion..."

$terminalStatus = $null
for ($attempt = 1; $attempt -le 360; $attempt++) {
    $status = aws ssm get-command-invocation `
        --profile $Profile `
        --region $Region `
        --command-id $commandId `
        --instance-id $InstanceId `
        --query "Status" `
        --output text 2>$null

    if ($status -in @("Success", "Failed", "Cancelled", "TimedOut")) {
        $terminalStatus = $status
        break
    }

    if ($attempt % 6 -eq 0) {
        Write-Host "SSM status: $status ($($attempt * 10) seconds)"
    }

    Start-Sleep -Seconds 10
}

if (-not $terminalStatus) {
    throw "GPU validation did not finish within 60 minutes."
}

$result = aws ssm get-command-invocation `
    --profile $Profile `
    --region $Region `
    --command-id $commandId `
    --instance-id $InstanceId `
    --output json | ConvertFrom-Json

Write-Host ""
Write-Host "=== GPU validation output ===" -ForegroundColor Cyan
Write-Host $result.StandardOutputContent

if ($result.StandardErrorContent) {
    Write-Host "=== GPU validation errors ===" -ForegroundColor Yellow
    Write-Host $result.StandardErrorContent
}

if ($result.Status -ne "Success") {
    throw "GPU validation failed with status $($result.Status)."
}

Write-Host "GPU validation completed successfully." -ForegroundColor Green
