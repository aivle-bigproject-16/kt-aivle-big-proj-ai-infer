param(
    [switch]$Execute,
    [string]$Profile = "default",
    [string]$Region = "ap-northeast-2",
    [string]$AccountId = "825555019742",
    [string]$Repository = "kt-aivle-big-proj-ai-infer",
    [string]$Tag = "onnx-ff1eccd"
)

$ErrorActionPreference = "Stop"
$localImage = "kt-aivle-big-proj-ai-infer:gpu-onnx-local"
$registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$remoteImage = "${registry}/${Repository}:${Tag}"

$imageId = docker image inspect $localImage --format '{{.Id}}' 2>$null
if ($LASTEXITCODE -ne 0 -or -not $imageId) {
    throw "Local GPU image was not found: $localImage"
}

Write-Host "Local image: $localImage"
Write-Host "Local ID: $imageId"
Write-Host "Target: $remoteImage"

if (-not $Execute) {
    Write-Host "`nDRY RUN: no ECR image was written." -ForegroundColor Yellow
    Write-Host "Run again with -Execute to publish."
    exit 0
}

aws ecr describe-repositories `
    --profile $Profile `
    --region $Region `
    --repository-names $Repository | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "ECR repository does not exist: $Repository"
}

aws ecr get-login-password `
    --profile $Profile `
    --region $Region |
    docker login `
        --username AWS `
        --password-stdin $registry
if ($LASTEXITCODE -ne 0) {
    throw "ECR login failed."
}

docker tag $localImage $remoteImage
docker push $remoteImage
if ($LASTEXITCODE -ne 0) {
    throw "ECR push failed."
}

aws ecr describe-images `
    --profile $Profile `
    --region $Region `
    --repository-name $Repository `
    --image-ids "imageTag=$Tag" `
    --query "imageDetails[0].{Digest:imageDigest,Size:imageSizeInBytes,Tags:imageTags}" `
    --output table
if ($LASTEXITCODE -ne 0) {
    throw "Published ECR image verification failed."
}

Write-Host "GPU image publish passed: $remoteImage" -ForegroundColor Green
