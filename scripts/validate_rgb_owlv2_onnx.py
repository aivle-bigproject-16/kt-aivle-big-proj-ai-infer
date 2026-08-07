import argparse
import json
from pathlib import Path

from rgb_ext_infer import Config, ExtInspector
from rgb_ext_infer_onnx import OnnxExtInspector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare pinned PyTorch and ONNX RGB defect outputs",
    )
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("models/rgb_owlv2_onnx"),
    )
    parser.add_argument("--glob", default="**/*")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--bbox-tolerance", type=float, default=8.0)
    parser.add_argument("--score-tolerance", type=float, default=0.002)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("rgb_owlv2_onnx_validation.json"),
    )
    return parser.parse_args()


def compare_frame(
    expected: dict,
    actual: dict,
    bbox_tolerance: float,
    score_tolerance: float,
) -> list[str]:
    errors = []

    if expected["판정"] != actual["판정"]:
        errors.append(
            f"verdict: {expected['판정']} != {actual['판정']}"
        )

    expected_defects = expected["결함"]
    actual_defects = actual["결함"]

    if len(expected_defects) != len(actual_defects):
        errors.append(
            f"defect count: {len(expected_defects)} != "
            f"{len(actual_defects)}"
        )
        return errors

    for index, (left, right) in enumerate(
        zip(expected_defects, actual_defects)
    ):
        if left["유형후보"] != right["유형후보"]:
            errors.append(
                f"defect[{index}] type: {left['유형후보']} != "
                f"{right['유형후보']}"
            )

        bbox_delta = max(
            abs(float(a) - float(b))
            for a, b in zip(
                left["위치"]["bbox"],
                right["위치"]["bbox"],
            )
        )
        score_delta = abs(float(left["_score"]) - float(right["_score"]))

        if bbox_delta > bbox_tolerance:
            errors.append(
                f"defect[{index}] bbox delta {bbox_delta} > "
                f"{bbox_tolerance}"
            )

        if score_delta > score_tolerance:
            errors.append(
                f"defect[{index}] score delta {score_delta} > "
                f"{score_tolerance}"
            )

    return errors


def main() -> int:
    args = parse_args()
    paths = sorted(
        path
        for path in args.images.glob(args.glob)
        if path.is_file()
    )

    if not paths:
        raise RuntimeError("No RGB validation images found")

    names = [path.name for path in paths]
    config = Config(device=args.device)
    pytorch_results = ExtInspector(cfg=config).infer_frames(
        paths,
        names=names,
    )
    onnx_results = OnnxExtInspector(
        cfg=config,
        model_dir=str(args.model_dir),
        providers=(
            ("CUDAExecutionProvider", "CPUExecutionProvider")
            if args.device == "cuda"
            else ("CPUExecutionProvider",)
        ),
    ).infer_frames(paths, names=names)
    frames = []
    failure_count = 0

    for path, expected, actual in zip(
        paths,
        pytorch_results,
        onnx_results,
    ):
        errors = compare_frame(
            expected,
            actual,
            args.bbox_tolerance,
            args.score_tolerance,
        )
        failure_count += bool(errors)
        frames.append(
            {
                "file": path.name,
                "passed": not errors,
                "errors": errors,
                "pytorch": expected,
                "onnx": actual,
            }
        )

    report = {
        "images": len(paths),
        "passed": len(paths) - failure_count,
        "failed": failure_count,
        "bboxTolerance": args.bbox_tolerance,
        "scoreTolerance": args.score_tolerance,
        "frames": frames,
    }
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"RGB OWLv2 ONNX validation: "
        f"{report['passed']}/{report['images']} passed"
    )
    print(f"Report: {args.report}")
    return 1 if failure_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
