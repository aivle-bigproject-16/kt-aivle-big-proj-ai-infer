param(
    [switch]$Execute,
    [switch]$KeepInstance,
    [string]$InstanceId = "",
    [string]$Profile = "default",
    [string]$Region = "ap-northeast-2",
    [string]$RgbRepo = "$env:USERPROFILE\Documents\model-card-review\kt-aivle-big-proj-model-rgb",
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:AWS_CLI_FILE_ENCODING = "UTF-8"

$repo = Split-Path -Parent $PSScriptRoot
$fixtureJson = Join-Path $RgbRepo "golden_fixture_deploy.json"
$fixtureDir = Join-Path $RgbRepo "fixtures_deploy"
$bucket = "kt-aivle-big-proj-kks"
$accountId = "825555019742"
$image = "${accountId}.dkr.ecr.${Region}.amazonaws.com/kt-aivle-big-proj-ai-infer:onnx-cuda12-ort126"
$instanceStateFile = Join-Path $PSScriptRoot ".gpu-validation-instance-id"
$runId = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
# The EC2 validation role has read access to the existing bundle fixture prefix.
# Do not introduce a new S3 prefix without updating that role first.
$s3Prefix = "models/ai-infer/onnx-20260809-01/fixtures/rgb-golden-$runId"
$archiveKey = "$s3Prefix/fixtures.zip"

if (-not $ReportPath) {
    $ReportPath = Join-Path $repo "rgb-golden-validation-$runId.log"
}
$transcriptStarted = $false

function Stop-BeforeLaunch([string]$Message) {
    Set-Content -LiteralPath $ReportPath -Encoding UTF8 -Value @(
        "Stage: preflight",
        "Status: FAILED",
        "Reason: $Message",
        "No paid GPU instance was created."
    )
    throw $Message
}

if ($Region -ne "ap-northeast-2") {
    Stop-BeforeLaunch "RGB GPU validation infrastructure is pinned to ap-northeast-2."
}

if (-not (Test-Path -LiteralPath $fixtureJson -PathType Leaf)) {
    Stop-BeforeLaunch "Golden fixture JSON does not exist: $fixtureJson"
}
if (-not (Test-Path -LiteralPath $fixtureDir -PathType Container)) {
    Stop-BeforeLaunch "Golden fixture image directory does not exist: $fixtureDir"
}

$fixture = Get-Content -LiteralPath $fixtureJson -Raw -Encoding UTF8 | ConvertFrom-Json
$frames = @($fixture.frames.PSObject.Properties)
if ($frames.Count -ne 20) {
    Stop-BeforeLaunch "Expected 20 golden fixture frames, found $($frames.Count)."
}

foreach ($frame in $frames) {
    $path = Join-Path $fixtureDir $frame.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Stop-BeforeLaunch "Golden fixture image is missing: $path"
    }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant().Substring(0, 16)
    $expected = [string]$frame.Value.sha256
    if ($expected -and $actual -ne $expected.ToLowerInvariant()) {
        Stop-BeforeLaunch "Golden fixture image hash mismatch: $($frame.Name) ($actual != $expected)"
    }
}

Write-Host ""
Write-Host "RGB golden validation plan" -ForegroundColor Cyan
Write-Host "Fixture:     $fixtureJson"
Write-Host "Images:      $fixtureDir (20 verified)"
Write-Host "Instance:    $(if ($InstanceId) { "reuse $InstanceId" } else { "new temporary g6e.xlarge in $Region" })"
Write-Host "Container:   $image"
Write-Host "S3 staging:  s3://$bucket/$s3Prefix/"
Write-Host "Local report: $ReportPath"
Write-Host "Cleanup:     $(if ($KeepInstance) { 'S3 only; EC2 retained by request' } else { 'S3 and EC2, including validation failure' })"

if (-not $Execute) {
    Write-Host ""
    Write-Host "DRY RUN: no AWS resource was created and no chargeable validation was started." -ForegroundColor Yellow
    Write-Host "Run again with -Execute to start paid GPU validation."
    exit 0
}

$preflightFailures = [Collections.Generic.List[string]]::new()

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    $preflightFailures.Add("AWS CLI is not installed or is not on PATH.")
} else {
    aws sts get-caller-identity --profile $Profile --output json *> $null
    if ($LASTEXITCODE -ne 0) { $preflightFailures.Add("AWS credentials/profile validation failed: $Profile") }

    aws s3api head-bucket --bucket $bucket --profile $Profile *> $null
    if ($LASTEXITCODE -ne 0) { $preflightFailures.Add("S3 bucket access failed: $bucket") }

    aws ecr describe-images `
        --repository-name "kt-aivle-big-proj-ai-infer" `
        --image-ids "imageTag=onnx-cuda12-ort126" `
        --profile $Profile --region $Region *> $null
    if ($LASTEXITCODE -ne 0) { $preflightFailures.Add("ECR validation image is unavailable: $image") }

    $offering = aws ec2 describe-instance-type-offerings `
        --profile $Profile --region $Region --location-type region `
        --filters "Name=instance-type,Values=g6e.xlarge" `
        --query "InstanceTypeOfferings[0].InstanceType" --output text 2>$null
    if ($LASTEXITCODE -ne 0 -or $offering -ne "g6e.xlarge") {
        $preflightFailures.Add("g6e.xlarge is unavailable in $Region.")
    }

    $quota = aws service-quotas get-service-quota `
        --profile $Profile --region $Region --service-code ec2 `
        --quota-code L-DB2E81BA --query "Quota.Value" --output text 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $quota -or [double]$quota -lt 4) {
        $preflightFailures.Add("G/VT GPU instance quota is unavailable or lower than 4 vCPUs.")
    }

    aws ec2 describe-images --profile $Profile --region $Region `
        --image-ids "ami-0129578997743b406" *> $null
    if ($LASTEXITCODE -ne 0) { $preflightFailures.Add("Validation AMI is unavailable in $Region.") }

    aws ec2 describe-subnets --profile $Profile --region $Region `
        --subnet-ids "subnet-0cae4801c10281684" *> $null
    if ($LASTEXITCODE -ne 0) { $preflightFailures.Add("Validation subnet is unavailable.") }

    aws ec2 describe-security-groups --profile $Profile --region $Region `
        --group-ids "sg-085dcc74d14f00bbc" *> $null
    if ($LASTEXITCODE -ne 0) { $preflightFailures.Add("Validation security group is unavailable.") }

    aws iam get-instance-profile --profile $Profile `
        --instance-profile-name "kt-aivle-big-proj-ec2-ssm-role" *> $null
    if ($LASTEXITCODE -ne 0) { $preflightFailures.Add("Validation EC2 instance profile is unavailable or unreadable.") }
}

if ($preflightFailures.Count -gt 0) {
    Stop-BeforeLaunch "Preflight failed before any paid instance was created:`n- $($preflightFailures -join "`n- ")"
}

Write-Host "Preflight: PASS (fixtures, hashes, AWS identity, S3, ECR, EC2 offering/quota/network/role)" -ForegroundColor Green
Start-Transcript -LiteralPath "$ReportPath.lifecycle.log" -Force | Out-Null
$transcriptStarted = $true

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) "rgb-golden-$runId"
$stagingDir = Join-Path $tempRoot "golden"
$archivePath = Join-Path $tempRoot "fixtures.zip"
$parametersFile = Join-Path $tempRoot "ssm-parameters.json"
$instanceId = $InstanceId.Trim()
$uploaded = $false

try {
    New-Item -ItemType Directory -Path $stagingDir -Force | Out-Null
    Copy-Item -LiteralPath $fixtureJson -Destination (Join-Path $stagingDir "golden_fixture_deploy.json")
    New-Item -ItemType Directory -Path (Join-Path $stagingDir "fixtures_deploy") -Force | Out-Null
    foreach ($frame in $frames) {
        Copy-Item -LiteralPath (Join-Path $fixtureDir $frame.Name) -Destination (Join-Path $stagingDir "fixtures_deploy")
    }
    Compress-Archive -Path (Join-Path $stagingDir "*") -DestinationPath $archivePath -CompressionLevel Optimal

    aws s3 cp $archivePath "s3://$bucket/$archiveKey" `
        --profile $Profile --region $Region --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "Failed to upload golden fixture archive." }
    $uploaded = $true

    if ($instanceId) {
        if ($instanceId -notmatch "^i-[0-9a-f]+$") {
            throw "Invalid reusable validation instance ID: $instanceId"
        }
        $existingInstance = aws ec2 describe-instances `
            --profile $Profile --region $Region --instance-ids $instanceId `
            --query "Reservations[0].Instances[0].{State:State.Name,Type:InstanceType,Name:Tags[?Key=='Name']|[0].Value}" `
            --output json | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0 -or -not $existingInstance) {
            throw "Reusable validation instance lookup failed: $instanceId"
        }
        if ($existingInstance.State -ne "running" -or
            $existingInstance.Type -ne "g6e.xlarge" -or
            $existingInstance.Name -ne "ai-infer-gpu-validation") {
            throw "Reusable instance safety check failed: state=$($existingInstance.State), type=$($existingInstance.Type), name=$($existingInstance.Name)"
        }
        $pingStatus = aws ssm describe-instance-information `
            --profile $Profile --region $Region `
            --filters "Key=InstanceIds,Values=$instanceId" `
            --query "InstanceInformationList[0].PingStatus" --output text
        if ($LASTEXITCODE -ne 0 -or $pingStatus -ne "Online") {
            throw "SSM is not online for reusable instance $instanceId."
        }
        Write-Warning "Reusing billable GPU instance: $instanceId"
    } else {
        & (Join-Path $PSScriptRoot "launch-gpu-validation.ps1") `
            -Execute -Profile $Profile -Region $Region
        if ($LASTEXITCODE -ne 0) { throw "Failed to launch GPU validation instance." }

        $instanceId = (Get-Content -LiteralPath $instanceStateFile -Raw).Trim()
        if ($instanceId -notmatch "^i-[0-9a-f]+$") {
            throw "Invalid validation instance ID: $instanceId"
        }
    }

    $archiveKey64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($archiveKey))
    $image64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($image))

    $remoteScript = @'
set -euo pipefail
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONIOENCODING=utf-8

ARCHIVE_KEY="$(printf '%s' "$1" | base64 -d)"
IMAGE="$(printf '%s' "$2" | base64 -d)"
BUCKET="kt-aivle-big-proj-kks"
REGION="ap-northeast-2"
WORK_DIR="/opt/rgb-golden-validation"
LOG="$WORK_DIR/rgb-golden-validation.log"

sudo rm -rf "$WORK_DIR"
sudo mkdir -p "$WORK_DIR"
sudo chown "$(id -u):$(id -g)" "$WORK_DIR"

exec > >(tee -a "$LOG") 2>&1

aws s3 cp "s3://${BUCKET}/${ARCHIVE_KEY}" "$WORK_DIR/fixtures.zip" --region "$REGION"
python3 - "$WORK_DIR/fixtures.zip" "$WORK_DIR" <<'PY'
import sys
import zipfile
import shutil
from pathlib import Path

archive = Path(sys.argv[1])
target = Path(sys.argv[2]).resolve()
with zipfile.ZipFile(archive) as zf:
    for member in zf.infolist():
        normalized_name = member.filename.replace("\\", "/")
        destination = (target / normalized_name).resolve()
        if target != destination and target not in destination.parents:
            raise RuntimeError(f"unsafe archive member: {member.filename}")
        if member.is_dir() or normalized_name.endswith("/"):
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as source, destination.open("wb") as output:
            shutil.copyfileobj(source, output)
PY

nvidia-smi
aws ecr get-login-password --region "$REGION" | sudo docker login \
  --username AWS --password-stdin "825555019742.dkr.ecr.${REGION}.amazonaws.com"
sudo docker pull "$IMAGE"

set +e
sudo docker run --rm --gpus all \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e HF_HOME=/cache/huggingface \
  -v "$WORK_DIR:/golden:ro" \
  -v "$WORK_DIR/hf-cache:/cache/huggingface" \
  --entrypoint python \
  "$IMAGE" /app/rgb_ext_infer.py \
    --verify-fixture \
    --fixture /golden/golden_fixture_deploy.json \
    --images /golden/fixtures_deploy
validation_exit=$?
set -e

exit "$validation_exit"
'@

    $script64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript))
    $command = "echo $script64 | base64 -d > /tmp/run-rgb-golden.sh && chmod 700 /tmp/run-rgb-golden.sh && sudo bash /tmp/run-rgb-golden.sh '$archiveKey64' '$image64'"
    $parameters = @{ commands = @($command) } | ConvertTo-Json -Depth 4
    [IO.File]::WriteAllText(
        $parametersFile,
        $parameters,
        [Text.UTF8Encoding]::new($false)
    )
    $parametersUri = "file://" + $parametersFile.Replace("\", "/")

    $commandId = aws ssm send-command `
        --profile $Profile --region $Region `
        --instance-ids $instanceId `
        --document-name "AWS-RunShellScript" `
        --comment "RGB 20-frame golden fixture validation" `
        --timeout-seconds 5400 `
        --parameters $parametersUri `
        --query "Command.CommandId" --output text
    if ($LASTEXITCODE -ne 0 -or -not $commandId) { throw "Failed to send SSM validation command." }

    Write-Host "SSM command: $commandId"
    $status = ""
    for ($attempt = 1; $attempt -le 540; $attempt++) {
        $status = aws ssm get-command-invocation `
            --profile $Profile --region $Region `
            --command-id $commandId --instance-id $instanceId `
            --query "Status" --output text 2>$null
        if ($status -in @("Success", "Failed", "Cancelled", "TimedOut")) { break }
        if ($attempt % 6 -eq 0) { Write-Host "SSM status: $status ($($attempt * 10) seconds)" }
        Start-Sleep -Seconds 10
    }
    if ($status -notin @("Success", "Failed", "Cancelled", "TimedOut")) {
        throw "RGB golden validation did not finish within 90 minutes."
    }

    $responseCode = aws ssm get-command-invocation `
        --profile $Profile --region $Region `
        --command-id $commandId --instance-id $instanceId `
        --query "ResponseCode" --output text
    $standardOutput = aws ssm get-command-invocation `
        --profile $Profile --region $Region `
        --command-id $commandId --instance-id $instanceId `
        --query "StandardOutputContent" --output text | Out-String
    $standardError = aws ssm get-command-invocation `
        --profile $Profile --region $Region `
        --command-id $commandId --instance-id $instanceId `
        --query "StandardErrorContent" --output text | Out-String
    $diagnostic = @(
        "Status: $status",
        "ResponseCode: $responseCode",
        "--- STDOUT ---",
        [string]$standardOutput,
        "--- STDERR ---",
        [string]$standardError
    ) -join "`r`n"
    Set-Content -LiteralPath $ReportPath -Value $diagnostic -Encoding UTF8

    Write-Host $standardOutput
    if ($standardError.Trim()) { Write-Warning $standardError }

    if ($status -ne "Success") {
        throw "RGB golden validation failed with SSM status $status. SSM stdout/stderr: $ReportPath"
    }
    Write-Host "RGB golden validation: PASS" -ForegroundColor Green
    Write-Host "Report: $ReportPath"
}
finally {
    if (-not $instanceId -and (Test-Path -LiteralPath $instanceStateFile)) {
        $candidateInstanceId = (Get-Content -LiteralPath $instanceStateFile -Raw).Trim()
        if ($candidateInstanceId -match "^i-[0-9a-f]+$") {
            $instanceId = $candidateInstanceId
        }
    }
    if ($instanceId -and -not $KeepInstance) {
        try {
            & (Join-Path $PSScriptRoot "terminate-gpu-validation.ps1") `
                -Execute -InstanceId $instanceId -Profile $Profile -Region $Region
        } catch {
            Write-Warning "URGENT: automatic EC2 termination failed for $instanceId. Terminate it manually to stop billing. $($_.Exception.Message)"
        }
    } elseif ($instanceId) {
        Write-Warning "GPU instance retained by request and is still billable: $instanceId"
    }
    if ($uploaded) {
        try {
            aws s3 rm "s3://$bucket/$s3Prefix/" --recursive `
                --profile $Profile --region $Region --only-show-errors | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "aws s3 rm exited with $LASTEXITCODE" }
        } catch {
            Write-Warning "Temporary S3 cleanup failed: s3://$bucket/$s3Prefix/. $($_.Exception.Message)"
        }
    }
    try {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force
        }
    } catch {
        Write-Warning "Local temporary-file cleanup failed: $tempRoot. $($_.Exception.Message)"
    }
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch { Write-Warning $_.Exception.Message }
    }
}
