import argparse
import hashlib
import json
import sys
from pathlib import Path


DEFAULT_MODEL_ID = "google/owlv2-large-patch14-ensemble"
DEFAULT_REVISION = "95e26936e865f87db1742128404b3c035d47d89d"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the pinned RGB OWLv2 detector to ONNX",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/rgb_owlv2_onnx"),
    )
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument(
        "--dtype",
        choices=("fp32", "fp16"),
        default="fp32",
    )
    parser.add_argument("--local-files-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    if args.dtype == "fp16" and args.device != "cuda":
        raise ValueError("fp16 export requires --device cuda")

    import onnx
    import torch
    from PIL import Image
    from transformers import Owlv2ForObjectDetection, Owlv2Processor

    from rgb_ext_infer import NEG_MAP, QUERY_MAP

    args.output.mkdir(parents=True, exist_ok=True)
    processor = Owlv2Processor.from_pretrained(
        args.model_id,
        revision=args.revision,
        local_files_only=args.local_files_only,
    )
    model = Owlv2ForObjectDetection.from_pretrained(
        args.model_id,
        revision=args.revision,
        local_files_only=args.local_files_only,
    ).eval().to(args.device)
    queries = [
        query
        for values in (*QUERY_MAP.values(), *NEG_MAP.values())
        for query in values
    ]
    encoded = processor(
        text=[queries],
        images=[Image.new("RGB", (960, 960), (0, 0, 0))],
        return_tensors="pt",
    ).to(args.device)

    if args.dtype == "fp16":
        model = model.half()
        encoded["pixel_values"] = encoded["pixel_values"].half()

    class ExportWrapper(torch.nn.Module):
        def __init__(self, wrapped):
            super().__init__()
            self.wrapped = wrapped

        def forward(self, input_ids, pixel_values, attention_mask):
            result = self.wrapped(
                input_ids=input_ids,
                pixel_values=pixel_values,
                attention_mask=attention_mask,
            )
            return result.logits, result.pred_boxes

    model_path = args.output / "model.onnx"
    export_model = ExportWrapper(model).eval()
    torch.onnx.export(
        export_model,
        (
            encoded["input_ids"],
            encoded["pixel_values"],
            encoded["attention_mask"],
        ),
        model_path,
        input_names=["input_ids", "pixel_values", "attention_mask"],
        output_names=["logits", "pred_boxes"],
        opset_version=18,
        dynamo=True,
        external_data=True,
        verify=True,
        report=True,
        artifacts_dir=str(args.output),
    )
    onnx.checker.check_model(str(model_path))
    processor.save_pretrained(args.output)
    models = sorted(args.output.glob("*.onnx"))

    if len(models) != 1:
        raise RuntimeError(
            f"Expected one exported ONNX file, found {len(models)}"
        )

    metadata = {
        "modelId": args.model_id,
        "revision": args.revision,
        "task": "zero-shot-object-detection",
        "opset": 18,
        "dtype": args.dtype,
        "batchSize": 1,
        "queryCount": len(queries),
        "onnxFile": models[0].name,
        "onnxSha256": sha256(models[0]),
        "artifactSha256": {
            path.name: sha256(path)
            for path in sorted(args.output.glob("model.onnx*"))
        },
        "queryMap": QUERY_MAP,
        "negativeMap": NEG_MAP,
    }
    metadata_path = args.output / "export_metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"ONNX: {models[0]}")
    print(f"SHA-256: {metadata['onnxSha256']}")
    print(f"Metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
