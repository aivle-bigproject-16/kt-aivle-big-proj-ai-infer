from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
from PIL import Image

from rgb_ext_infer import DROP_TAGS, ExtInspector


def resolve_onnx_model(model_dir: str | Path) -> Path:
    model_dir = Path(model_dir)
    models = sorted(model_dir.glob("*.onnx"))

    if len(models) != 1:
        raise RuntimeError(
            f"RGB OWLv2 directory must contain exactly one ONNX model; "
            f"found {len(models)} in {model_dir}"
        )

    return models[0]


def build_session_feed(
    encoded: Mapping[str, object],
    required_inputs: set[str],
) -> dict[str, object]:
    missing = sorted(required_inputs.difference(encoded))

    if missing:
        raise ValueError(
            "OWLv2 processor did not produce required ONNX inputs: "
            + ", ".join(missing)
        )

    return {
        name: encoded[name]
        for name in required_inputs
    }


def postprocess_owlv2(
    logits: np.ndarray,
    pred_boxes: np.ndarray,
    target_sizes: Sequence[Sequence[int]],
    threshold: float,
) -> list[dict[str, np.ndarray]]:
    """Apply the OWLv2 zero-shot detection postprocessing in NumPy."""
    probabilities = 1.0 / (1.0 + np.exp(-np.clip(logits, -80.0, 80.0)))
    scores = probabilities.max(axis=-1)
    labels = probabilities.argmax(axis=-1)
    center_x, center_y, width, height = np.moveaxis(pred_boxes, -1, 0)
    corner_boxes = np.stack(
        (
            center_x - width / 2.0,
            center_y - height / 2.0,
            center_x + width / 2.0,
            center_y + height / 2.0,
        ),
        axis=-1,
    )
    results = []

    for index, (image_height, image_width) in enumerate(target_sizes):
        keep = scores[index] > threshold
        scale = np.asarray(
            [image_width, image_height, image_width, image_height],
            dtype=corner_boxes.dtype,
        )
        results.append(
            {
                "scores": scores[index][keep],
                "labels": labels[index][keep],
                "boxes": corner_boxes[index][keep] * scale,
            }
        )

    return results


@dataclass
class OnnxExtInspector(ExtInspector):
    """OWLv2 inspector that preserves the source preprocessing contract."""

    model_dir: str = "/models/rgb_owlv2_onnx"
    providers: Sequence[str] | None = None
    _session: object = field(default=None, init=False, repr=False)

    def load(self):
        if self._session is not None:
            return self

        import onnxruntime as ort
        from transformers import Owlv2Processor

        model_dir = Path(self.model_dir)
        model_path = resolve_onnx_model(model_dir)
        available = set(ort.get_available_providers())
        requested = list(
            self.providers
            or ("CUDAExecutionProvider", "CPUExecutionProvider")
        )
        selected = [provider for provider in requested if provider in available]

        if not selected:
            raise RuntimeError(
                "No requested ONNX Runtime provider is available"
            )

        self._proc = Owlv2Processor.from_pretrained(
            model_dir,
            local_files_only=True,
        )
        self._session = ort.InferenceSession(
            str(model_path),
            providers=selected,
        )
        return self

    def _detect(self, crops: Sequence[Image.Image]):
        self.load()
        c = self.cfg
        output: list[list[tuple]] = [[] for _ in crops]
        input_names = {
            item.name
            for item in self._session.get_inputs()
        }
        output_names = [
            item.name
            for item in self._session.get_outputs()
        ]

        # The export fixes batch size to one because text query tensors are
        # flattened as batch * query_count by the OWLv2 processor.
        for start in range(len(crops)):
            block = [crops[start]]
            squares = []
            sizes = []

            for image in block:
                side = max(image.size)
                canvas = Image.new("RGB", (side, side), (0, 0, 0))
                canvas.paste(image, (0, 0))
                squares.append(canvas)
                sizes.append([side, side])

            encoded = self._proc(
                text=[self._queries] * len(squares),
                images=squares,
                return_tensors="np",
            )
            feed = build_session_feed(encoded, input_names)
            values = self._session.run(None, feed)
            raw_outputs = {
                name: value
                for name, value in zip(output_names, values)
            }

            for required in ("logits", "pred_boxes"):
                if required not in raw_outputs:
                    raise RuntimeError(
                        f"RGB OWLv2 ONNX output is missing {required}"
                    )

            results = postprocess_owlv2(
                logits=raw_outputs["logits"],
                pred_boxes=raw_outputs["pred_boxes"],
                target_sizes=sizes,
                threshold=min(c.thr_gate, c.thr_loc) * 0.5,
            )

            for index, result in enumerate(results):
                boxes = []

                for box, score, label in zip(
                    result["boxes"].tolist(),
                    result["scores"].tolist(),
                    result["labels"].tolist(),
                ):
                    tag = self._tag_of[self._queries[label]]

                    if tag in DROP_TAGS:
                        continue

                    boxes.append(
                        (
                            box[0],
                            box[1],
                            box[2],
                            box[3],
                            float(score),
                            tag,
                        )
                    )

                boxes.sort(key=lambda item: -item[4])
                output[start + index] = boxes

        return output
