from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_SOURCE_V1 = DATA_DIR / "labels" / "datav1"
DEFAULT_SOURCE_V2 = DATA_DIR / "training" / "datav2_ready"
DEFAULT_DESTINATION = DATA_DIR / "training" / "datav1_v2_combined"
TARGET_NAMES = ["abnormal", "normal"]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class Source:
    key: str
    root: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Gabungkan dataset mata entok v1 dan v2 tanpa mengubah sumber. "
            "Class ID dipetakan berdasarkan nama kelas."
        )
    )
    parser.add_argument("--source-v1", type=Path, default=DEFAULT_SOURCE_V1)
    parser.add_argument("--source-v2", type=Path, default=DEFAULT_SOURCE_V2)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--version", default="1.0.0")
    return parser.parse_args()


def normalise_names(raw_names) -> list[str]:
    if isinstance(raw_names, dict):
        return [str(raw_names[index]) for index in range(len(raw_names))]
    return [str(name) for name in (raw_names or [])]


def load_source_config(source: Source) -> tuple[dict, Path, dict[int, int]]:
    yaml_path = source.root / "data.yaml"
    if not yaml_path.is_file():
        raise FileNotFoundError(f"data.yaml sumber tidak ditemukan: {yaml_path}")

    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    names = normalise_names(data.get("names"))
    if not names:
        raise ValueError(f"Daftar kelas kosong: {yaml_path}")

    class_map: dict[int, int] = {}
    for source_id, name in enumerate(names):
        if name not in TARGET_NAMES:
            raise ValueError(f"Kelas tidak didukung '{name}' di {yaml_path}")
        class_map[source_id] = TARGET_NAMES.index(name)

    raw_root = Path(str(data.get("path") or source.root))
    dataset_root = raw_root if raw_root.is_absolute() else yaml_path.parent / raw_root
    return data, dataset_root.resolve(), class_map


def label_for_image(image_path: Path) -> Path:
    if image_path.parent.name.lower() == "images":
        return image_path.parent.parent / "labels" / f"{image_path.stem}.txt"
    if image_path.parent.parent.name.lower() == "images":
        root = image_path.parent.parent.parent
        return root / "labels" / image_path.parent.name / f"{image_path.stem}.txt"
    raise ValueError(f"Struktur gambar YOLO tidak didukung: {image_path}")


def split_images(data: dict, dataset_root: Path, split: str) -> list[Path]:
    raw_value = data.get(split)
    if not raw_value:
        raise ValueError(f"Split '{split}' tidak ditemukan")
    values = raw_value if isinstance(raw_value, list) else [raw_value]
    images: list[Path] = []
    for value in values:
        path = Path(str(value))
        path = path if path.is_absolute() else dataset_root / path
        path = path.resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"Folder split tidak ditemukan: {path}")
        images.extend(
            item.resolve()
            for item in sorted(path.rglob("*"))
            if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES
        )
    return images


def remap_label(
    label_path: Path,
    class_map: dict[int, int],
    allow_empty: bool,
) -> tuple[str, Counter[int]]:
    if not label_path.is_file():
        raise FileNotFoundError(f"Label tidak ditemukan: {label_path}")

    lines = [
        line.strip()
        for line in label_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if not lines:
        if not allow_empty:
            raise ValueError(f"Label kosong tidak diizinkan: {label_path}")
        return "", Counter()

    mapped_lines: list[str] = []
    counts: Counter[int] = Counter()
    for line_number, line in enumerate(lines, start=1):
        parts = line.split()
        location = f"{label_path}:{line_number}"
        if len(parts) != 5:
            raise ValueError(f"Format label bukan YOLO 5 kolom: {location}")
        try:
            source_id = int(parts[0])
            x_center, y_center, width, height = map(float, parts[1:])
        except ValueError as error:
            raise ValueError(f"Nilai label tidak valid: {location}") from error
        if source_id not in class_map:
            raise ValueError(f"Class ID di luar pemetaan: {location}")
        if not (
            0 <= x_center <= 1
            and 0 <= y_center <= 1
            and 0 < width <= 1
            and 0 < height <= 1
            and x_center - width / 2 >= -1e-6
            and x_center + width / 2 <= 1 + 1e-6
            and y_center - height / 2 >= -1e-6
            and y_center + height / 2 <= 1 + 1e-6
        ):
            raise ValueError(f"Bounding box keluar batas: {location}")

        target_id = class_map[source_id]
        counts[target_id] += 1
        mapped_lines.append(f"{target_id} {' '.join(parts[1:])}")

    return "\n".join(mapped_lines) + "\n", counts


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def link_or_copy(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def build_dataset(
    sources: list[Source],
    destination: Path,
    version: str,
) -> dict:
    destination = destination.resolve()
    build_root = destination.with_name(f"{destination.name}.building")
    if destination.exists() or build_root.exists():
        raise FileExistsError(
            "Target sudah ada; hapus atau arsipkan secara eksplisit sebelum membangun ulang: "
            f"{destination}"
        )

    for split in ("train", "val", "test"):
        (build_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (build_root / "labels" / split).mkdir(parents=True, exist_ok=True)

    manifest_rows: list[list] = []
    duplicates: list[dict] = []
    seen_images: dict[str, tuple[str, str, str]] = {}
    split_counts = {
        split: {"images": 0, "backgrounds": 0, "boxes": Counter()}
        for split in ("train", "val", "test")
    }

    try:
        for source in sources:
            data, dataset_root, class_map = load_source_config(source)
            allow_empty = bool(data.get("allow_empty_labels", False))
            split_key = {"train": "train", "val": "val", "test": "test"}
            if "val" not in data and "valid" in data:
                split_key["val"] = "valid"

            for target_split, source_split in split_key.items():
                for image_path in split_images(data, dataset_root, source_split):
                    label_path = label_for_image(image_path)
                    label_text, box_counts = remap_label(
                        label_path, class_map, allow_empty
                    )
                    with Image.open(image_path) as image:
                        image.verify()
                    with Image.open(image_path) as image:
                        width, height = image.size

                    image_hash = sha256_file(image_path)
                    label_hash = sha256_bytes(label_text.encode("utf-8"))
                    previous = seen_images.get(image_hash)
                    if previous:
                        previous_split, previous_label_hash, previous_name = previous
                        if previous_split != target_split:
                            raise ValueError(
                                "Gambar identik berada di dua split: "
                                f"{previous_name} ({previous_split}) dan "
                                f"{image_path} ({target_split})"
                            )
                        if previous_label_hash != label_hash:
                            raise ValueError(
                                "Gambar identik memiliki label berbeda setelah pemetaan: "
                                f"{previous_name} dan {label_path}"
                            )
                        duplicates.append(
                            {
                                "source": source.key,
                                "split": target_split,
                                "image": str(image_path),
                                "duplicate_of": previous_name,
                            }
                        )
                        continue

                    output_name = f"{source.key}__{image_path.name}"
                    output_image = build_root / "images" / target_split / output_name
                    output_label = (
                        build_root
                        / "labels"
                        / target_split
                        / f"{Path(output_name).stem}.txt"
                    )
                    if output_image.exists() or output_label.exists():
                        raise FileExistsError(f"Nama output bertabrakan: {output_name}")

                    link_or_copy(image_path, output_image)
                    output_label.write_text(label_text, encoding="utf-8")
                    seen_images[image_hash] = (
                        target_split,
                        label_hash,
                        str(image_path),
                    )
                    split_counts[target_split]["images"] += 1
                    split_counts[target_split]["boxes"].update(box_counts)
                    if not box_counts:
                        split_counts[target_split]["backgrounds"] += 1
                    manifest_rows.append(
                        [
                            target_split,
                            f"images/{target_split}/{output_name}",
                            f"labels/{target_split}/{output_label.name}",
                            source.key,
                            str(image_path),
                            width,
                            height,
                            image_hash,
                            label_hash,
                            box_counts[0],
                            box_counts[1],
                        ]
                    )

        for split, values in split_counts.items():
            if values["images"] == 0:
                raise ValueError(f"Split {split} kosong")
            for class_id, class_name in enumerate(TARGET_NAMES):
                if values["boxes"][class_id] == 0:
                    raise ValueError(f"Split {split} tidak memiliki kelas {class_name}")

        data_yaml = {
            "path": destination.as_posix(),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "nc": len(TARGET_NAMES),
            "names": {index: name for index, name in enumerate(TARGET_NAMES)},
            "allow_empty_labels": True,
            "split_grouping": "original_id",
        }
        (build_root / "data.yaml").write_text(
            yaml.safe_dump(data_yaml, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        (build_root / "VERSION").write_text(f"{version}\n", encoding="utf-8")

        metadata_dir = build_root / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        with (metadata_dir / "manifest.csv").open(
            "w", encoding="utf-8", newline=""
        ) as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "split",
                    "image",
                    "label",
                    "source_dataset",
                    "source_image",
                    "width",
                    "height",
                    "image_sha256",
                    "label_sha256",
                    "boxes_abnormal",
                    "boxes_normal",
                ]
            )
            writer.writerows(manifest_rows)
        (metadata_dir / "duplicates.json").write_text(
            json.dumps(duplicates, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        summary = {
            "dataset_version": version,
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "sources": {source.key: str(source.root.resolve()) for source in sources},
            "classes": TARGET_NAMES,
            "class_mapping": {
                "datav1": {"0": "abnormal", "1": "normal"},
                "datav2": {"0": "normal -> target class 1"},
            },
            "duplicate_images_excluded": len(duplicates),
            "splits": {
                split: {
                    "images": values["images"],
                    "backgrounds": values["backgrounds"],
                    "boxes_by_class": {
                        name: values["boxes"][index]
                        for index, name in enumerate(TARGET_NAMES)
                    },
                }
                for split, values in split_counts.items()
            },
        }
        (metadata_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (metadata_dir / "TEST_SET_LOCKED.md").write_text(
            "# Test Set Terkunci\n\n"
            "Jangan gunakan split test untuk tuning. Gunakan hanya untuk evaluasi "
            "akhir setelah memilih checkpoint dari validation.\n",
            encoding="utf-8",
        )
        (build_root / "README.md").write_text(
            "# Dataset gabungan mata entok datav1 + datav2\n\n"
            "Dataset sumber tidak diubah. Pemetaan kelas target:\n\n"
            "- `0`: `abnormal`\n"
            "- `1`: `normal`\n\n"
            "Pada datav2, class sumber `0=normal` dipetakan menjadi class target `1`.\n"
            "Gambar dibuat sebagai hardlink bila didukung filesystem; label ditulis ulang "
            "setelah validasi dan pemetaan class ID.\n",
            encoding="utf-8",
        )

        build_root.rename(destination)
        return summary
    except Exception:
        if build_root.exists():
            shutil.rmtree(build_root)
        raise


def main() -> int:
    args = parse_args()
    sources = [
        Source("datav1", args.source_v1.resolve()),
        Source("datav2", args.source_v2.resolve()),
    ]
    summary = build_dataset(sources, args.destination, args.version)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
