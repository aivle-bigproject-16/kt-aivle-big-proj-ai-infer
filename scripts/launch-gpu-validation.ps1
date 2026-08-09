param(
    [switch]$Execute,
    [string]$Profile = "default",
    [string]$Region = "ap-northeast-2"
)

$ErrorActionPreference = "Stop"

$amiId = "ami-0129578997743b406"
$instanceType = "g6e.xlarge"
$subnetId = "subnet-0cae4801c10281684"
$securityGroupId = "sg-085dcc74d14f00bbc"
$instanceProfile = "kt-aivle-big-proj-ec2-ssm-role"
$instanceName = "ai-infer-gpu-validation"
$volumeSize = 150

Write-Host ""
Write-Host "GPU EC2 launch plan" -ForegroundColor Cyan
Write-Host "AMI:              $amiId"
Write-Host "Instance type:    $instanceType"
Write-Host "Subnet:           $subnetId"
Write-Host "Security group:   $securityGroupId"
Write-Host "Instance profile: $instanceProfile"
Write-Host "Root volume:      $volumeSize GiB gp3 encrypted"
Write-Host "Public IP:        enabled"
Write-Host "Ingress:          none"
Write-Host "Region:           $Region"

$quota = aws service-quotas get-service-quota `
    --profile $Profile `
    --region $Region `
    --service-code ec2 `
    --quota-code L-DB2E81BA `
    --query "Quota.Value" `
    --output text

if ($LASTEXITCODE -ne 0) {
    throw "GPU quota lookup failed."
}

if ([double]$quota -lt 4) {
    throw "GPU quota is lower than the required 4 vCPUs."
}

$existing = aws ec2 describe-instances `
    --profile $Profile `
    --region $Region `
    --filters `
        "Name=tag:Name,Values=$instanceName" `
        "Name=instance-state-name,Values=pending,running,stopping,stopped" `
    --query "Reservations[].Instances[].InstanceId" `
    --output text

if ($LASTEXITCODE -ne 0) {
    throw "Existing instance lookup failed."
}

if ($existing) {
    throw "An existing validation instance was found: $existing"
}

if (-not $Execute) {
    Write-Host ""
    Write-Host "DRY RUN: no EC2 instance was created." `
        -ForegroundColor Yellow
    Write-Host "Use -Execute only for the final paid validation."
    exit 0
}

Write-Host ""
Write-Host "WARNING: paid GPU EC2 creation starts now." `
    -ForegroundColor Yellow

$instanceId = aws ec2 run-instances `
    --profile $Profile `
    --region $Region `
    --image-id $amiId `
    --instance-type $instanceType `
    --subnet-id $subnetId `
    --security-group-ids $securityGroupId `
    --iam-instance-profile "Name=$instanceProfile" `
    --associate-public-ip-address `
    --metadata-options `
        "HttpTokens=required,HttpEndpoint=enabled" `
    --block-device-mappings `
        "DeviceName=/dev/sda1,Ebs={VolumeSize=$volumeSize,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}" `
    --tag-specifications `
        "ResourceType=instance,Tags=[{Key=Name,Value=$instanceName},{Key=Purpose,Value=temporary-gpu-validation}]" `
        "ResourceType=volume,Tags=[{Key=Name,Value=$instanceName},{Key=Purpose,Value=temporary-gpu-validation}]" `
    --count 1 `
    --query "Instances[0].InstanceId" `
    --output text

if ($LASTEXITCODE -ne 0 -or -not $instanceId) {
    throw "GPU EC2 creation failed."
}

$stateFile = Join-Path $PSScriptRoot ".gpu-validation-instance-id"

[IO.File]::WriteAllText(
    $stateFile,
    $instanceId.Trim(),
    [Text.UTF8Encoding]::new($false)
)

Write-Host ""
Write-Host "Instance created: $instanceId" `
    -ForegroundColor Green
Write-Host "Billing has started." `
    -ForegroundColor Yellow
Write-Host "State file: $stateFile"

aws ec2 wait instance-status-ok `
    --profile $Profile `
    --region $Region `
    --instance-ids $instanceId

if ($LASTEXITCODE -ne 0) {
    throw "Instance status check failed. Inspect or terminate the instance immediately."
}

Write-Host ""
Write-Host "GPU EC2 status checks passed." `
    -ForegroundColor Green
Write-Host "Instance ID: $instanceId"