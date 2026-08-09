$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$image = "kt-aivle-big-proj-ai-infer:onnx-local"
$ctFixtureDir = Join-Path $env:USERPROFILE "Documents\model-card-review\kt-aivle-big-proj-model-ct\fixtures"
$rgbFixtureDir = Join-Path $env:USERPROFILE "Documents\rgb-unified-api-fixture"
$network = "onnx-api-validation"
$fixtureContainer = "onnx-fixtures"
$serverContainer = "onnx-unified-server"

Set-Location $repo

Write-Host "`n=== 필수 파일 확인 ===" -ForegroundColor Cyan
$requiredPaths = @(
    (Join-Path $repo "models\quality_ct.onnx"),
    (Join-Path $repo "models\defect_ct.torch211.onnx"),
    (Join-Path $repo "models\quality_rgb.onnx"),
    (Join-Path $repo "models\rgb_owlv2_onnx\model.onnx"),
    (Join-Path $repo "models\rgb_owlv2_onnx\model.onnx.data"),
    (Join-Path $ctFixtureDir "golden_ct.jpg")
)

foreach ($path in $requiredPaths) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "필수 파일이 없습니다: $path"
    }
}

$rgbImage = Get-ChildItem -LiteralPath $rgbFixtureDir -Recurse -File |
    Where-Object { $_.Extension -match '^\.(jpg|jpeg|png)$' } |
    Select-Object -First 1

if (-not $rgbImage) {
    throw "RGB 검증 이미지가 없습니다: $rgbFixtureDir"
}

$rgbBasePath = (Resolve-Path -LiteralPath $rgbFixtureDir).Path.TrimEnd("\") + "\"
$rgbFullPath = (Resolve-Path -LiteralPath $rgbImage.FullName).Path

if (-not $rgbFullPath.StartsWith($rgbBasePath, [StringComparison]::OrdinalIgnoreCase)) {
    throw "RGB 이미지가 픽스처 폴더 내부에 있지 않습니다."
}

$rgbRelativePath = $rgbFullPath.Substring($rgbBasePath.Length).Replace("\", "/")
Write-Host "RGB 이미지: $rgbRelativePath"

Write-Host "`n=== Docker 상태 확인 ===" -ForegroundColor Cyan
docker version --format '{{.Server.Version}}'
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop이 실행되지 않았습니다."
}

$imageId = docker images --quiet $image
if (-not $imageId) {
    throw "로컬 이미지가 없습니다: $image"
}

Write-Host "`n=== 기존 검증 리소스 정리 ===" -ForegroundColor Cyan
$containerNames = @(docker ps -a --format '{{.Names}}')
if ($containerNames -contains $serverContainer) {
    docker rm -f $serverContainer | Out-Null
}
if ($containerNames -contains $fixtureContainer) {
    docker rm -f $fixtureContainer | Out-Null
}

$networkNames = @(docker network ls --format '{{.Name}}')
if ($networkNames -notcontains $network) {
    docker network create $network | Out-Null
}

Write-Host "`n=== 픽스처 서버 기동 ===" -ForegroundColor Cyan
docker run -d `
    --name $fixtureContainer `
    --network $network `
    --mount "type=bind,source=$ctFixtureDir,target=/srv/ct,readonly" `
    --mount "type=bind,source=$rgbFixtureDir,target=/srv/rgb,readonly" `
    python:3.12-slim `
    python -m http.server 8080 --directory /srv | Out-Null

if ($LASTEXITCODE -ne 0) {
    throw "픽스처 서버 기동에 실패했습니다."
}

Write-Host "`n=== 통합 ONNX 서버 기동 ===" -ForegroundColor Cyan
docker run -d `
    --name $serverContainer `
    --network $network `
    -p 8000:8000 `
    --mount "type=bind,source=$repo\models,target=/models,readonly" `
    --env "INFERENCE_MODE=onnx" `
    --env "CT_QUALITY_MODEL_PATH=/models/quality_ct.onnx" `
    --env "CT_DEFECT_MODEL_PATH=/models/defect_ct.torch211.onnx" `
    --env "CT_POSTPROCESS_TYPE=NMS" `
    --env "CT_POSTPROCESS_MATCH_METRIC=IOS" `
    --env "CT_POSTPROCESS_MATCH_THRESHOLD=0.44" `
    --env "RGB_QUALITY_MODEL_PATH=/models/quality_rgb.onnx" `
    --env "RGB_DEFECT_MODEL_DIR=/models/rgb_owlv2_onnx" `
    $image | Out-Null

if ($LASTEXITCODE -ne 0) {
    throw "통합 ONNX 서버 기동에 실패했습니다."
}

Write-Host "`n=== 서버 준비 대기 ===" -ForegroundColor Cyan
$ready = $false
$health = $null

for ($attempt = 1; $attempt -le 180; $attempt++) {
    $state = docker inspect --format '{{.State.Status}}' $serverContainer 2>$null
    if ($state -eq "exited") {
        docker logs --tail 200 $serverContainer
        throw "통합 ONNX 서버 초기화에 실패했습니다."
    }

    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5
        $ready = $true
        break
    }
    catch {
        if (($attempt % 10) -eq 0) {
            Write-Host "대기 중: $attempt / 180"
        }
        Start-Sleep -Seconds 2
    }
}

if (-not $ready) {
    docker logs --tail 200 $serverContainer
    throw "6분 안에 서버가 준비되지 않았습니다."
}

Write-Host "`n=== Health ===" -ForegroundColor Cyan
$health | ConvertTo-Json -Depth 10

$ctBody = @{
    inspection_id = 2001
    image_key = "fixtures/ct/golden_ct.jpg"
    image_url = "http://${fixtureContainer}:8080/ct/golden_ct.jpg"
} | ConvertTo-Json

Write-Host "`n=== CT 추론 ===" -ForegroundColor Cyan
$ctResponse = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/infer/ct" `
    -ContentType "application/json" `
    -Body $ctBody `
    -TimeoutSec 300
$ctResponse | ConvertTo-Json -Depth 20

$rgbBody = @{
    inspection_id = 2002
    image_key = "fixtures/rgb/$rgbRelativePath"
    image_url = "http://${fixtureContainer}:8080/rgb/$rgbRelativePath"
} | ConvertTo-Json

Write-Host "`n=== RGB 추론 ===" -ForegroundColor Cyan
$rgbResponse = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/infer/rgb" `
    -ContentType "application/json" `
    -Body $rgbBody `
    -TimeoutSec 900
$rgbResponse | ConvertTo-Json -Depth 20

foreach ($item in @(
    @{ Name = "CT"; Response = $ctResponse },
    @{ Name = "RGB"; Response = $rgbResponse }
)) {
    $name = $item.Name
    $response = $item.Response
    $properties = @($response.PSObject.Properties.Name)

    if ($response.label -notin @("PASS", "REJECT", "FAIL")) {
        throw "$name label 계약 위반: $($response.label)"
    }
    if ($properties -notcontains "defects") {
        throw "$name 응답에 defects가 없습니다."
    }
    if ($properties -contains "defect_type") {
        throw "$name 응답에 폐기된 defect_type이 있습니다."
    }
    if ($properties -contains "bbox") {
        throw "$name 응답에 폐기된 최상위 bbox가 있습니다."
    }
}

Write-Host "`n=== 최근 서버 로그 ===" -ForegroundColor Cyan
docker logs --tail 150 $serverContainer

Write-Host "`nCT + RGB 통합 ONNX API 검증 통과" -ForegroundColor Green
Write-Host "컨테이너는 로그 확인을 위해 유지했습니다."
