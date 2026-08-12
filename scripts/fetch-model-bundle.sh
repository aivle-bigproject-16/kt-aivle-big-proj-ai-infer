#!/usr/bin/env bash
#
# S3 에 올려 둔 모델 번들을 배포 호스트로 내려받는다.
# scripts/upload-model-bundle.ps1 의 역방향이고, 같은 매니페스트를 정본으로 쓴다.
#
# 이 스크립트가 필요한 이유는 ai-infer 가 기동 시점에 S3 에서 가중치를 받지 않기
# 때문이다. app/core/settings.py 는 로컬 경로(/models/...)만 읽는다. 따라서 컨테이너를
# 띄우기 전에 호스트에 번들을 받아 두고 /models 로 마운트해야 한다.
#
# 배포 호스트는 리눅스라 PowerShell 스크립트를 쓸 수 없다. 그래서 bash 로 따로 둔다.
#
# 사용 예:
#   ./scripts/fetch-model-bundle.sh
#   ./scripts/fetch-model-bundle.sh --target /opt/battery/models
#   ./scripts/fetch-model-bundle.sh --profile admin --force
#
# 내려받은 경로를 compose 의 MODELS_DIR 로 준다.
#   MODELS_DIR=/opt/battery/models
#
# EC2 에서는 인스턴스 프로파일로 인증하므로 --profile 을 주지 않는다.
# 로컬에서는 models/ 프리픽스 읽기 권한이 있는 자격 증명이 필요하다.
# 정책 AivleAiInferS3Policy 가 그 범위를 갖고 있다.

set -euo pipefail

TARGET_DIR="./models"
BUCKET="kt-aivle-big-proj-kks"
REGION="ap-northeast-2"
PROFILE=""
MANIFEST=""
FORCE=0

usage() {
    cat <<'EOF'
Usage: fetch-model-bundle.sh [options]

  --target DIR     Destination directory (default: ./models)
  --bucket NAME    S3 bucket (default: kt-aivle-big-proj-kks)
  --region NAME    AWS region (default: ap-northeast-2)
  --profile NAME   AWS CLI profile (default: none, use the ambient credentials)
  --manifest PATH  Manifest file (default: <repo>/deployment/model-manifest.json)
  --force          Re-download artifacts that already match the manifest
  -h, --help       Show this message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)   TARGET_DIR="$2"; shift 2 ;;
        --bucket)   BUCKET="$2";     shift 2 ;;
        --region)   REGION="$2";     shift 2 ;;
        --profile)  PROFILE="$2";    shift 2 ;;
        --manifest) MANIFEST="$2";   shift 2 ;;
        --force)    FORCE=1;         shift ;;
        -h|--help)  usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

if [[ -z "$MANIFEST" ]]; then
    MANIFEST="$REPO_DIR/deployment/model-manifest.json"
fi

for tool in aws python3 sha256sum; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Required tool not found: $tool" >&2
        exit 1
    fi
done

if [[ ! -f "$MANIFEST" ]]; then
    echo "Manifest not found: $MANIFEST" >&2
    exit 1
fi

# --profile 은 값이 있을 때만 넘긴다. 빈 문자열을 넘기면 CLI 가 프로필 이름으로 읽는다.
aws_args=(--region "$REGION")
if [[ -n "$PROFILE" ]]; then
    aws_args+=(--profile "$PROFILE")
fi

# 매니페스트를 탭 구분 레코드로 펼친다. jq 는 배포 호스트에 없을 수 있어 python3 을 쓴다.
read_manifest() {
    python3 - "$MANIFEST" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    manifest = json.load(handle)

print("\t".join([
    "#bundle",
    manifest["bundleVersion"],
    manifest["s3Prefix"],
    str(len(manifest["artifacts"])),
]))

for artifact in manifest["artifacts"]:
    print("\t".join([
        artifact["name"],
        artifact["s3Key"],
        artifact["localPath"],
        str(artifact["sizeBytes"]),
        artifact["sha256"],
    ]))
PY
}

# tr 로 CR 을 떼는 이유는 윈도우에서 개발자가 이 스크립트를 돌릴 때다.
# Git Bash 의 python3 은 줄끝을 CRLF 로 내보내므로, 그대로 두면 마지막 필드인
# sha256 값 끝에 CR 이 붙어 비교가 무조건 실패한다. 배포 호스트(리눅스)에서는
# 원래 붙지 않으니 이 처리는 무해하다.
MANIFEST_ROWS="$(read_manifest | tr -d '\r')"

BUNDLE_VERSION="$(printf '%s\n' "$MANIFEST_ROWS" | awk -F'\t' '$1=="#bundle"{print $2}')"
ARTIFACT_COUNT="$(printf '%s\n' "$MANIFEST_ROWS" | awk -F'\t' '$1=="#bundle"{print $4}')"

mkdir -p "$TARGET_DIR"
TARGET_ABS="$(cd "$TARGET_DIR" && pwd)"

echo "Bundle:    $BUNDLE_VERSION"
echo "Bucket:    s3://$BUCKET"
echo "Region:    $REGION"
echo "Target:    $TARGET_ABS"
echo "Artifacts: $ARTIFACT_COUNT"
echo

downloaded=0
skipped=0

while IFS=$'\t' read -r name s3_key local_path size_bytes sha256; do
    [[ "$name" == "#bundle" ]] && continue
    [[ -z "$name" ]] && continue

    # localPath 는 models/quality_ct.onnx 처럼 models/ 로 시작한다. 그 앞부분을 떼고
    # 대상 디렉터리 밑에 놓는다. 컨테이너가 이 디렉터리를 /models 로 마운트하므로
    # 결과 경로가 설정값(CT_QUALITY_MODEL_PATH 등)과 그대로 일치한다.
    relative="${local_path#models/}"
    dest="$TARGET_ABS/$relative"

    if [[ $FORCE -eq 0 && -f "$dest" ]]; then
        actual_size="$(stat -c %s "$dest")"
        if [[ "$actual_size" == "$size_bytes" ]]; then
            actual_hash="$(sha256sum "$dest" | cut -d' ' -f1)"
            if [[ "$actual_hash" == "$sha256" ]]; then
                echo "SKIP $name (already present and verified)"
                skipped=$((skipped + 1))
                continue
            fi
        fi
        echo "STALE $name (size or checksum differs, re-downloading)"
    fi

    mkdir -p "$(dirname "$dest")"

    echo "GET  $name  s3://$BUCKET/$s3_key"
    aws s3 cp "s3://$BUCKET/$s3_key" "$dest" "${aws_args[@]}" --only-show-errors

    actual_size="$(stat -c %s "$dest")"
    if [[ "$actual_size" != "$size_bytes" ]]; then
        echo "Size mismatch: $name (expected $size_bytes, got $actual_size)" >&2
        exit 1
    fi

    actual_hash="$(sha256sum "$dest" | cut -d' ' -f1)"
    if [[ "$actual_hash" != "$sha256" ]]; then
        echo "SHA-256 mismatch: $name" >&2
        echo "  expected $sha256" >&2
        echo "  actual   $actual_hash" >&2
        exit 1
    fi

    echo "OK   $name  $actual_size  $actual_hash"
    downloaded=$((downloaded + 1))
done <<< "$MANIFEST_ROWS"

echo
echo "Downloaded: $downloaded"
echo "Skipped:    $skipped"
echo "Model bundle fetch and verification passed."
echo
echo "Set MODELS_DIR=$TARGET_ABS in the infra .env file."
