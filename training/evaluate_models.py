from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = (
    PROJECT_ROOT
    / "experiments"
    / "active"
    / "entok_eye_datav1_v2_yolo26s_960"
    / "weights"
    / "best.pt"
)
DEFAULT_BASELINE = (
    PROJECT_ROOT / "src" / "entok_vision" / "models" / "entok_normal_abnormal.pt"
)
DEFAULT_DATA = PROJECT_ROOT / "data" / "training" / "datav1_v2_combined" / "data.yaml"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "evaluation" / "model_comparison.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bandingkan kandidat YOLO26s dengan model produksi pada test set terkunci."
    )
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--min-abnormal-recall-gain", type=float, default=0.0)
    parser.add_argument("--max-map-drop", type=float, default=0.0)
    return parser.parse_args()


def _number(value: Any) -> float:
    if hasattr(value, "item"):
        value = value.item()
    return float(value)


def prepare_dataset_config(data_path: Path, output_dir: Path) -> Path:
    payload = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Konfigurasi dataset tidak valid: {data_path}")

    configured_root = Path(str(payload.get("path", ".")))
    dataset_root = (
        configured_root.resolve()
        if configured_root.is_absolute()
        else (data_path.parent / configured_root).resolve()
    )
    for split in ("train", "val", "test"):
        split_value = payload.get(split)
        if not split_value:
            raise ValueError(f"Dataset tidak memiliki split {split!r}.")
        split_paths = split_value if isinstance(split_value, list) else [split_value]
        for value in split_paths:
            candidate = Path(str(value))
            candidate = candidate if candidate.is_absolute() else dataset_root / candidate
            if not candidate.exists():
                raise FileNotFoundError(
                    f"Path split {split!r} tidak ditemukan: {candidate.resolve()}"
                )

    resolved_payload = dict(payload)
    resolved_payload["path"] = str(dataset_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_path = output_dir / "resolved_test_dataset.yaml"
    resolved_path.write_text(
        yaml.safe_dump(resolved_payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return resolved_path


def _class_rows(metrics: Any, model: YOLO) -> list[dict[str, Any]]:
    summary_method = getattr(metrics, "summary", None)
    if callable(summary_method):
        rows = summary_method()
        if isinstance(rows, list) and rows:
            normalized = []
            for row in rows:
                class_name = str(row.get("Class", row.get("class", ""))).lower()
                normalized.append(
                    {
                        "class": class_name,
                        "precision": _number(row.get("Box-P", row.get("precision", 0))),
                        "recall": _number(row.get("Box-R", row.get("recall", 0))),
                        "map50": _number(row.get("Box-mAP50", row.get("mAP50", 0))),
                        "map50_95": _number(
                            row.get("Box-mAP50-95", row.get("mAP50-95", 0))
                        ),
                    }
                )
            return normalized

    names = getattr(metrics, "names", None) or getattr(model, "names", {})
    names = names if isinstance(names, dict) else dict(enumerate(names))
    box = metrics.box
    class_ids = list(getattr(box, "ap_class_index", range(len(names))))
    rows = []
    for result_index, class_id in enumerate(class_ids):
        precision, recall, map50, map50_95 = box.class_result(result_index)
        rows.append(
            {
                "class": str(names[int(class_id)]).lower(),
                "precision": _number(precision),
                "recall": _number(recall),
                "map50": _number(map50),
                "map50_95": _number(map50_95),
            }
        )
    return rows


def evaluate(
    label: str,
    model_path: Path,
    data_path: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    if not model_path.is_file():
        raise FileNotFoundError(f"Model {label} tidak ditemukan: {model_path}")
    model = YOLO(str(model_path.resolve()))
    kwargs: dict[str, Any] = {
        "data": str(data_path.resolve()),
        "split": "test",
        "imgsz": args.imgsz,
        "workers": args.workers,
        "project": str((args.output.parent / "runs").resolve()),
        "name": label,
        "exist_ok": True,
        "verbose": False,
    }
    if args.device not in {"", "auto", "none"}:
        kwargs["device"] = args.device
    metrics = model.val(**kwargs)
    return {
        "model_path": str(model_path.resolve()),
        "overall": {
            "precision": _number(metrics.box.mp),
            "recall": _number(metrics.box.mr),
            "map50": _number(metrics.box.map50),
            "map50_95": _number(metrics.box.map),
        },
        "classes": _class_rows(metrics, model),
    }


def _class_recall(result: dict[str, Any], class_name: str) -> float:
    for row in result["classes"]:
        if row["class"] == class_name.lower():
            return float(row["recall"])
    raise ValueError(f"Kelas {class_name!r} tidak ditemukan pada hasil evaluasi.")


def main() -> int:
    args = parse_args()
    for path in (args.candidate, args.baseline, args.data):
        if not path.is_file():
            raise FileNotFoundError(path)
    evaluation_data = prepare_dataset_config(args.data.resolve(), args.output.parent)
    baseline = evaluate("baseline", args.baseline, evaluation_data, args)
    candidate = evaluate("candidate", args.candidate, evaluation_data, args)
    baseline_abnormal = _class_recall(baseline, "abnormal")
    candidate_abnormal = _class_recall(candidate, "abnormal")
    recall_gain = candidate_abnormal - baseline_abnormal
    map_delta = candidate["overall"]["map50_95"] - baseline["overall"]["map50_95"]
    passed = (
        recall_gain >= args.min_abnormal_recall_gain
        and map_delta >= -args.max_map_drop
    )
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data": str(args.data.resolve()),
        "resolved_data": str(evaluation_data.resolve()),
        "split": "test",
        "imgsz": args.imgsz,
        "device": args.device,
        "baseline": baseline,
        "candidate": candidate,
        "gate": {
            "abnormal_recall_gain": recall_gain,
            "map50_95_delta": map_delta,
            "min_abnormal_recall_gain": args.min_abnormal_recall_gain,
            "max_map_drop": args.max_map_drop,
            "passed": passed,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["gate"], indent=2))
    print(f"Laporan: {args.output.resolve()}")
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
