param(
    [switch]$Execute,
    [string]$CtImagePath = "",
    [string]$RgbImagePath = "",
    [string]$Profile = "default",
    [string]$Region = "ap-northeast-2"
)

$ErrorActionPreference = "Stop"

$bucket = "kt-aivle-big-proj-kks"
$prefix = "models/ai-infer/onnx-20260809-01/fixtures"
$stateFile = Join-Path $PSScriptRoot ".gpu-validation-fixtures.json"
$targets = @(
    @{ Name = "CT"; Source = $CtImagePath },
    @{ Name = "RGB"; Source = $RgbImagePath }
)

Write-Host ""
Write-Host "GPU validation fixture upload plan" -ForegroundColor Cyan
foreach ($target in $targets) {
    Write-Host "$($target.Name): $($target.Source)"
}

if (-not $Execute) {
    Write-Host ""
    Write-Host "DRY RUN: no fixture was uploaded." -ForegroundColor Yellow
    Write-Host "Provide -Execute, -CtImagePath, and -RgbImagePath immediately before GPU validation."
    exit 0
}

$uploaded = [ordered]@{}
foreach ($target in $targets) {
    if (-not $target.Source -or -not (Test-Path -LiteralPath $target.Source -PathType Leaf)) {
        throw "$($target.Name) fixture does not exist: $($target.Source)"
    }

    $file = Get-Item -LiteralPath $target.Source
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLower()
    $key = "$prefix/$($target.Name.ToLower())-$hash"
    $checksumBytes = for ($index = 0; $index -lt $hash.Length; $index += 2) {
        [Convert]::ToByte($hash.Substring($index, 2), 16)
    }
    $checksumBase64 = [Convert]::ToBase64String($checksumBytes)

    aws s3 cp `
        $file.FullName `
        "s3://$bucket/$key" `
        --profile $Profile `
        --region $Region `
        --sse AES256 `
        --checksum-algorithm SHA256 `
        --metadata "sha256=$hash,fixture=$($target.Name.ToLower())"

    if ($LASTEXITCODE -ne 0) {
        throw "$($target.Name) fixture upload failed."
    }

    $remote = aws s3api head-object `
        --profile $Profile `
        --region $Region `
        --bucket $bucket `
        --key $key `
        --checksum-mode ENABLED `
        --query "{Size:ContentLength,Sha256:Metadata.sha256,Checksum:ChecksumSHA256,Encryption:ServerSideEncryption}" `
        --output json | ConvertFrom-Json

    if ($LASTEXITCODE -ne 0) {
        throw "$($target.Name) fixture verification failed."
    }

    if (
        [long]$remote.Size -ne $file.Length -or
        $remote.Sha256 -ne $hash -or
        $remote.Checksum -ne $checksumBase64 -or
        $remote.Encryption -ne "AES256"
    ) {
        throw "$($target.Name) fixture verification failed."
    }

    $uploaded["$($target.Name)FixtureKey"] = $key
    $uploaded["$($target.Name)FixtureSha256"] = $hash
    Write-Host "PASS $($target.Name): s3://$bucket/$key size=$($file.Length) sha256=$hash" -ForegroundColor Green
}

[IO.File]::WriteAllText(
    $stateFile,
    ($uploaded | ConvertTo-Json),
    [Text.UTF8Encoding]::new($false)
)

Write-Host "Fixture state: $stateFile"
Write-Host "GPU validation fixtures uploaded and verified." -ForegroundColor Green
