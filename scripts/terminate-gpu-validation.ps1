param(
    [switch]$Execute,
    [string]$InstanceId = "",
    [string]$Profile = "default",
    [string]$Region = "ap-northeast-2"
)

$ErrorActionPreference = "Stop"

$expectedName = "ai-infer-gpu-validation"
$stateFile = Join-Path $PSScriptRoot ".gpu-validation-instance-id"

if (-not $InstanceId) {
    if (-not (Test-Path -LiteralPath $stateFile)) {
        throw "Instance ID was not provided and the state file does not exist."
    }

    $InstanceId = (
        Get-Content -LiteralPath $stateFile -Raw
    ).Trim()
}

if ($InstanceId -notmatch "^i-[0-9a-f]+$") {
    throw "Invalid EC2 instance ID: $InstanceId"
}

$instance = aws ec2 describe-instances `
    --profile $Profile `
    --region $Region `
    --instance-ids $InstanceId `
    --query "Reservations[0].Instances[0].{Id:InstanceId,State:State.Name,Type:InstanceType,Name:Tags[?Key=='Name']|[0].Value,Volumes:BlockDeviceMappings[].Ebs.VolumeId}" `
    --output json |
    ConvertFrom-Json

if ($LASTEXITCODE -ne 0 -or -not $instance) {
    throw "Validation instance lookup failed."
}

Write-Host ""
Write-Host "GPU EC2 termination plan" -ForegroundColor Cyan
Write-Host "Instance ID:   $($instance.Id)"
Write-Host "Name:          $($instance.Name)"
Write-Host "Type:          $($instance.Type)"
Write-Host "State:         $($instance.State)"
Write-Host "Volumes:       $($instance.Volumes -join ', ')"

if ($instance.Name -ne $expectedName) {
    throw "Safety check failed: unexpected Name tag '$($instance.Name)'."
}

if ($instance.Type -ne "g6e.xlarge") {
    throw "Safety check failed: unexpected instance type '$($instance.Type)'."
}

if ($instance.State -eq "terminated") {
    Write-Host ""
    Write-Host "Instance is already terminated." `
        -ForegroundColor Green

    if (Test-Path -LiteralPath $stateFile) {
        Remove-Item -LiteralPath $stateFile -Force
    }

    exit 0
}

if (-not $Execute) {
    Write-Host ""
    Write-Host "DRY RUN: no EC2 instance was terminated." `
        -ForegroundColor Yellow
    Write-Host "Use -Execute after GPU validation is complete."
    exit 0
}

Write-Host ""
Write-Host "Terminating validation instance..." `
    -ForegroundColor Yellow

aws ec2 terminate-instances `
    --profile $Profile `
    --region $Region `
    --instance-ids $InstanceId `
    --query "TerminatingInstances[].{Id:InstanceId,Previous:PreviousState.Name,Current:CurrentState.Name}" `
    --output table

if ($LASTEXITCODE -ne 0) {
    throw "GPU EC2 termination request failed."
}

aws ec2 wait instance-terminated `
    --profile $Profile `
    --region $Region `
    --instance-ids $InstanceId

if ($LASTEXITCODE -ne 0) {
    throw "Waiting for instance termination failed."
}

Write-Host ""
Write-Host "Instance terminated: $InstanceId" `
    -ForegroundColor Green

Start-Sleep -Seconds 5

foreach ($volumeId in @($instance.Volumes)) {
    if (-not $volumeId) {
        continue
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $volumeState = aws ec2 describe-volumes `
        --profile $Profile `
        --region $Region `
        --volume-ids $volumeId `
        --query "Volumes[0].State" `
        --output text 2>$null
    $describeVolumeExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference

    if ($describeVolumeExitCode -eq 0 -and $volumeState -and $volumeState -ne "None") {
        Write-Host "WARNING: volume still exists: $volumeId ($volumeState)" `
            -ForegroundColor Yellow
    }

    if ($describeVolumeExitCode -ne 0 -or -not $volumeState -or $volumeState -eq "None") {
        Write-Host "Volume deletion confirmed: $volumeId" `
            -ForegroundColor Green
    }
}

if (Test-Path -LiteralPath $stateFile) {
    Remove-Item -LiteralPath $stateFile -Force
}

Write-Host ""
Write-Host "GPU validation resource cleanup completed." `
    -ForegroundColor Green
