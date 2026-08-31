from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "artifacts" / "evaluation" / "model_comparison.json"
DEFAULT_CANDIDATE = (
    PROJECT_ROOT
    / "experiments"
    / "active"
    / "entok_eye_datav1_v2_yolo26s_960"
    / "weights"
    / "best.pt"
)
MODEL_DIR = PROJECT_ROOT / "src" / "entok_vision" / "models"
PRODUCTION_MODEL = MODEL_DIR / "entok_yolo26s_combined.pt"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promosikan kandidat hanya jika gate evaluasi test set lulus."
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if not bool(report.get("gate", {}).get("passed")):
        raise RuntimeError("Promosi ditolak: kandidat belum lulus gate evaluasi.")
    candidate = args.candidate.resolve()
    evaluated = Path(report["candidate"]["model_path"]).resolve()
    if candidate != evaluated:
        raise RuntimeError(
            "Promosi ditolak: file kandidat berbeda dari model yang dievaluasi."
        )
    if not candidate.is_file():
        raise FileNotFoundError(candidate)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    if PRODUCTION_MODEL.is_file():
        backup_dir = (
            PROJECT_ROOT
            / "artifacts"
            / "model-backups"
            / datetime.now().strftime("%Y%m%d-%H%M%S")
        )
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PRODUCTION_MODEL, backup_dir / PRODUCTION_MODEL.name)
    shutil.copy2(candidate, PRODUCTION_MODEL)
    checksum = _sha256(PRODUCTION_MODEL)

    manifest_path = MODEL_DIR / "manifest.yaml"
    manifest: dict[str, Any] = yaml.safe_load(
        manifest_path.read_text(encoding="utf-8")
    ) or {}
    models = [
        item
        for item in manifest.get("models", [])
        if isinstance(item, dict) and item.get("id") != "yolo26s-combined"
    ]
    models.insert(
        0,
        {
            "id": "yolo26s-combined",
            "file": PRODUCTION_MODEL.name,
            "sha256": checksum,
            "evaluation_report": "artifacts/evaluation/model_comparison.json",
        },
    )
    manifest.update(version="0.2.0", models=models)
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )
    (MODEL_DIR / "default_model.txt").write_text(
        "yolo26s-combined\n", encoding="utf-8"
    )
    print(f"Model produksi: {PRODUCTION_MODEL}")
    print(f"SHA-256: {checksum}")
    print("Default model: yolo26s-combined")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
