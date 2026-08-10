from pathlib import Path


SCRIPT = Path("scripts/run-rgb-golden-validation.ps1")


def test_rgb_golden_validation_is_paid_action_guarded_and_auto_cleaned():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "[switch]$Execute" in text
    assert "if (-not $Execute)" in text
    assert "DRY RUN: no AWS resource was created" in text
    assert "launch-gpu-validation.ps1" in text
    assert "terminate-gpu-validation.ps1" in text
    assert "finally {" in text
    assert "[switch]$KeepInstance" in text


def test_rgb_golden_validation_verifies_and_stages_all_20_frames():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "$frames.Count -ne 20" in text
    assert "Get-FileHash" in text
    assert ".Hash.ToLowerInvariant().Substring(0, 16)" in text
    assert "Compress-Archive" in text
    assert "aws s3 cp" in text
    assert "aws s3 rm" in text


def test_rgb_golden_validation_runs_cuda_and_preserves_exit_status():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "nvidia-smi" in text
    assert "docker run --rm --gpus all" in text
    assert "CUDA_VISIBLE_DEVICES=0" in text
    assert "--verify-fixture" in text
    assert "golden_fixture_deploy.json" in text
    assert "fixtures_deploy" in text
    assert "validation_exit=$?" in text
    assert "get-command-invocation" in text


def test_all_possible_preflight_checks_run_before_instance_creation():
    text = SCRIPT.read_text(encoding="utf-8")

    launch = text.index("& (Join-Path $PSScriptRoot \"launch-gpu-validation.ps1\")")
    for fragment in (
        "aws sts get-caller-identity",
        "aws s3api head-bucket",
        "aws ecr describe-images",
        "aws ec2 describe-instance-type-offerings",
        "aws service-quotas get-service-quota",
        "aws ec2 describe-images",
        "aws ec2 describe-subnets",
        "aws ec2 describe-security-groups",
        "aws iam get-instance-profile",
    ):
        assert text.index(fragment) < launch


def test_failure_diagnostics_are_saved_before_cleanup():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "trap upload_log EXIT" in text
    assert 'exec > >(tee -a "$LOG") 2>&1' in text
    assert "StandardOutputContent" in text
    assert "StandardErrorContent" in text
    assert "ResponseCode" in text
    assert "Set-Content -LiteralPath $ReportPath" in text
    assert "$ReportPath.lifecycle.log" in text
    assert "$ReportPath.remote.log" in text

    mkdir = text.index('sudo mkdir -p "$WORK_DIR"')
    logging = text.index('exec > >(tee -a "$LOG") 2>&1')
    assert mkdir < logging


def test_cleanup_attempts_ec2_before_other_resources_and_is_isolated():
    text = SCRIPT.read_text(encoding="utf-8")

    finally_block = text[text.index("finally {") :]
    assert finally_block.index("terminate-gpu-validation.ps1") < finally_block.index("aws s3 rm")
    assert finally_block.count("try {") >= 3
    assert "automatic EC2 termination failed" in finally_block


def test_region_is_pinned_before_paid_execution():
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'if ($Region -ne "ap-northeast-2")' in text
    assert text.index('if ($Region -ne "ap-northeast-2")') < text.index("if (-not $Execute)")
