$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $repo "deployment\model-manifest.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw |
    ConvertFrom-Json

Write-Host "Bundle: $($manifest.bundleVersion)"
Write-Host "Artifacts: $($manifest.artifacts.Count)"

foreach ($artifact in $manifest.artifacts) {
    $path = Join-Path $repo ($artifact.localPath.Replace("/", "\"))

    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing artifact: $($artifact.localPath)"
    }

    $file = Get-Item -LiteralPath $path
    if ($file.Length -ne $artifact.sizeBytes) {
        throw "Size mismatch: $($artifact.localPath)"
    }

    $actualHash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
    if ($actualHash -ne $artifact.sha256) {
        throw "SHA-256 mismatch: $($artifact.localPath)"
    }

    Write-Host "PASS $($artifact.name) $($file.Length) $actualHash"
}

Write-Host "Model manifest validation passed." -ForegroundColor Green
