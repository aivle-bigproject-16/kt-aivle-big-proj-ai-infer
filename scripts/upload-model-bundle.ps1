param(
    [switch]$Execute,
    [string]$Bucket = "kt-aivle-big-proj-kks",
    [string]$Profile = "default",
    [string]$Region = "ap-northeast-2"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $repo "deployment\model-manifest.json"
$verifyScript = Join-Path $PSScriptRoot "verify-model-manifest.ps1"
$manifest = Get-Content -LiteralPath $manifestPath -Raw |
    ConvertFrom-Json

& $verifyScript

Write-Host "`nUpload plan"
Write-Host "Bucket: $Bucket"
Write-Host "Region: $Region"
Write-Host "Bundle: $($manifest.bundleVersion)"

foreach ($artifact in $manifest.artifacts) {
    Write-Host "$($artifact.localPath) -> s3://$Bucket/$($artifact.s3Key)"
}

if (-not $Execute) {
    Write-Host "`nDRY RUN: no S3 objects were written." -ForegroundColor Yellow
    Write-Host "Run again with -Execute to upload."
    exit 0
}

aws sts get-caller-identity `
    --profile $Profile `
    --query "Account" `
    --output text | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "AWS authentication failed."
}

foreach ($artifact in $manifest.artifacts) {
    $source = Join-Path $repo ($artifact.localPath.Replace("/", "\"))
    $target = "s3://$Bucket/$($artifact.s3Key)"
    $metadata = "sha256=$($artifact.sha256),bundle-version=$($manifest.bundleVersion)"

    Write-Host "Uploading $($artifact.name)..."
    aws s3 cp `
        $source `
        $target `
        --profile $Profile `
        --region $Region `
        --sse AES256 `
        --metadata $metadata `
        --only-show-errors
    if ($LASTEXITCODE -ne 0) {
        throw "Upload failed: $($artifact.name)"
    }

    $headJson = aws s3api head-object `
        --profile $Profile `
        --region $Region `
        --bucket $Bucket `
        --key $artifact.s3Key `
        --output json
    if ($LASTEXITCODE -ne 0) {
        throw "HeadObject failed: $($artifact.name)"
    }

    $head = $headJson | ConvertFrom-Json
    if ([long]$head.ContentLength -ne [long]$artifact.sizeBytes) {
        throw "Uploaded size mismatch: $($artifact.name)"
    }
    if ($head.Metadata.sha256 -ne $artifact.sha256) {
        throw "Uploaded SHA-256 metadata mismatch: $($artifact.name)"
    }
}

$manifestKey = "$($manifest.s3Prefix)/model-manifest.json"
$manifestHash = (Get-FileHash `
    -LiteralPath $manifestPath `
    -Algorithm SHA256).Hash.ToLower()

Write-Host "Uploading deployment manifest..."
aws s3 cp `
    $manifestPath `
    "s3://$Bucket/$manifestKey" `
    --profile $Profile `
    --region $Region `
    --sse AES256 `
    --metadata "sha256=$manifestHash,bundle-version=$($manifest.bundleVersion)" `
    --content-type "application/json" `
    --only-show-errors
if ($LASTEXITCODE -ne 0) {
    throw "Deployment manifest upload failed."
}

$manifestHeadJson = aws s3api head-object `
    --profile $Profile `
    --region $Region `
    --bucket $Bucket `
    --key $manifestKey `
    --output json
if ($LASTEXITCODE -ne 0) {
    throw "Deployment manifest verification failed."
}

$manifestHead = $manifestHeadJson | ConvertFrom-Json
if ($manifestHead.Metadata.sha256 -ne $manifestHash) {
    throw "Deployment manifest SHA-256 metadata mismatch."
}

Write-Host "Model bundle upload and verification passed." -ForegroundColor Green
