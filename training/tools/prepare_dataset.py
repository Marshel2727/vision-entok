import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from PIL import Image


SPLIT_MAP = {"train": "train", "valid": "val", "test": "test"}
SPLIT_PRIORITY = {"train": 0, "val": 1, "test": 2}


@dataclass(frozen=True)
class Record:
    source_split: str
    target_split: str
    image: Path
    label: Path
    family: str
    original_id: str
    split_group: str
    width: int
    height: int
    image_sha256: str
    label_sha256: str
    class_counts: dict[int, int]


def original_id(image_path: Path) -> str:
    return image_path.stem.split(".rf.", 1)[0]


def source_family(image_path: Path) -> str:
    return re.sub(
        r"[-_]\d+_(?:jpg|jpeg|png)$",
        "",
        original_id(image_path),
        flags=re.IGNORECASE,
    )


def label_for_source_image(image_path: Path) -> Path:
    if image_path.parent.name.lower() != "images":
        raise ValueError(f"Folder sumber gambar harus bernama images: {image_path}")
    return image_path.parent.parent / "labels" / f"{image_path.stem}.txt"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_names(source_root: Path) -> list[str]:
    with (source_root / "data.yaml").open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    raw_names = data.get("names") or []
    if isinstance(raw_names, dict):
        return [str(raw_names[index]) for index in range(len(raw_names))]
    return [str(name) for name in raw_names]


def validate_label(label_path: Path, class_count: int) -> dict[int, int]:
    if not label_path.is_file():
        raise FileNotFoundError(f"Label tidak ditemukan: {label_path}")

    counts: Counter[int] = Counter()
    lines = [line.strip() for line in label_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"Label kosong tidak dimasukkan sebagai negatif tanpa verifikasi: {label_path}")

    for line_number, line in enumerate(lines, start=1):
        parts = line.split()
        location = f"{label_path}:{line_number}"
        if len(parts) != 5:
            raise ValueError(f"Format label bukan YOLO 5 kolom: {location}")
        try:
            class_id = int(parts[0])
            x_center, y_center, width, height = map(float, parts[1:])
        except ValueError as error:
            raise ValueError(f"Nilai label tidak valid: {location}") from error
        if class_id not in range(class_count):
            raise ValueError(f"Class ID di luar rentang: {location}")
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
            raise ValueError(f"Bounding box keluar batas gambar: {location}")
        counts[class_id] += 1
    return dict(counts)


def read_boxes(label_path: Path) -> list[tuple[int, float, float, float, float]]:
    boxes = []
    for line in label_path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        parts = line.split()
        boxes.append((int(parts[0]), *(float(value) for value in parts[1:])))
    return sorted(boxes)


def labels_equivalent(previous: Record, current: Record, tolerance_pixels: float = 1.5) -> bool:
    previous_boxes = read_boxes(previous.label)
    current_boxes = read_boxes(current.label)
    if len(previous_boxes) != len(current_boxes):
        return False
    scales = (1.0, previous.width, previous.height, previous.width, previous.height)
    for left, right in zip(previous_boxes, current_boxes, strict=True):
        if left[0] != right[0]:
            return False
        if any(abs(left[index] - right[index]) * scales[index] > tolerance_pixels for index in range(1, 5)):
            return False
    return True


def load_source_records(source_root: Path, names: list[str], grouping: str, exclude_empty_labels: bool) -> tuple[list[dict], list[dict]]:
    records: list[dict] = []
    excluded: list[dict] = []
    for source_split, target_split in SPLIT_MAP.items():
        manifest = source_root / "splits_grouped" / f"{source_split}.txt"
        if manifest.is_file():
            image_paths = [Path(line.strip()).resolve() for line in manifest.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        else:
            image_dir = source_root / source_split / "images"
            if not image_dir.is_dir():
                raise FileNotFoundError(f"Folder split sumber tidak ditemukan: {image_dir}")
            image_paths = sorted(path.resolve() for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"})
        for image_path in image_paths:
            label_path = label_for_source_image(image_path)
            if not image_path.is_file():
                raise FileNotFoundError(f"Gambar tidak ditemukan: {image_path}")
            if not label_path.is_file():
                raise FileNotFoundError(f"Label tidak ditemukan: {label_path}")
            if not label_path.read_text(encoding="utf-8-sig").strip():
                if not exclude_empty_labels:
                    raise ValueError(f"Label kosong perlu review manual: {label_path}")
                excluded.append(
                    {
                        "file": image_path.name,
                        "family": source_family(image_path),
                        "source_split": target_split,
                        "owner_split": target_split,
                        "category": "needs_reannotation",
                        "reason": "label kosong tetapi visual QA menunjukkan potensi objek mata; tidak dijadikan background",
                    }
                )
                continue
            with Image.open(image_path) as image:
                image.verify()
            with Image.open(image_path) as image:
                width, height = image.size
            records.append(
                {
                    "source_split": source_split,
                    "target_split": target_split,
                    "image": image_path,
                    "label": label_path,
                    "family": source_family(image_path),
                    "original_id": original_id(image_path),
                    "split_group": source_family(image_path) if grouping == "source_family" else original_id(image_path),
                    "width": width,
                    "height": height,
                    "image_sha256": sha256_file(image_path),
                    "label_sha256": sha256_file(label_path),
                    "class_counts": validate_label(label_path, len(names)),
                }
            )
    return records, excluded


def select_without_source_leakage(raw_records: list[dict]) -> tuple[list[Record], list[dict]]:
    splits_by_group: dict[str, set[str]] = defaultdict(set)
    for record in raw_records:
        splits_by_group[record["split_group"]].add(record["target_split"])

    owner_by_group = {
        group: max(splits, key=lambda split: SPLIT_PRIORITY[split])
        for group, splits in splits_by_group.items()
    }
    selected: list[Record] = []
    excluded: list[dict] = []
    for raw in raw_records:
        owner = owner_by_group[raw["split_group"]]
        if raw["target_split"] != owner:
            excluded.append(
                {
                    "file": raw["image"].name,
                    "family": raw["family"],
                    "source_split": raw["target_split"],
                    "owner_split": owner,
                    "category": "source_leakage",
                    "reason": "dikeluarkan agar satu sumber/sesi tidak muncul di dua split",
                }
            )
            continue
        selected.append(Record(**raw))
    return selected, excluded


def remove_exact_duplicates(records: list[Record], excluded: list[dict]) -> list[Record]:
    unique: list[Record] = []
    seen: dict[str, Record] = {}
    for record in sorted(records, key=lambda item: (item.target_split, item.original_id, item.image.name)):
        previous = seen.get(record.image_sha256)
        if not previous:
            seen[record.image_sha256] = record
            unique.append(record)
            continue
        if previous.target_split != record.target_split:
            raise ValueError(f"Duplikat gambar berada di dua split: {previous.image} dan {record.image}")
        if previous.label_sha256 != record.label_sha256 and not labels_equivalent(previous, record):
            raise ValueError(f"Gambar identik memiliki label berbeda: {previous.label} dan {record.label}")
        excluded.append(
            {
                "file": record.image.name,
                "family": record.family,
                "source_split": record.target_split,
                "owner_split": record.target_split,
                "category": "exact_duplicate",
                "reason": f"duplikat byte-identik dari {previous.image.name}; label identik/ekuivalen <=1.5 px",
            }
        )
    return unique


def validate_selection(records: list[Record], names: list[str]) -> None:
    groups_by_split: dict[str, set[str]] = defaultdict(set)
    hashes: dict[str, Record] = {}
    filenames: set[str] = set()
    class_counts_by_split: dict[str, Counter[int]] = defaultdict(Counter)

    for record in records:
        groups_by_split[record.target_split].add(record.split_group)
        if record.image.name in filenames:
            raise ValueError(f"Nama file bertabrakan pada dataset canonical: {record.image.name}")
        filenames.add(record.image.name)
        previous = hashes.get(record.image_sha256)
        if previous:
            raise ValueError(f"Duplikat gambar identik tersisa: {previous.image} dan {record.image}")
        hashes[record.image_sha256] = record
        class_counts_by_split[record.target_split].update(record.class_counts)

    for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
        overlap = groups_by_split[left] & groups_by_split[right]
        if overlap:
            raise ValueError(f"Data leakage sumber {left}/{right}: {sorted(overlap)}")

    for split in ("train", "val", "test"):
        if not groups_by_split[split]:
            raise ValueError(f"Split {split} kosong")
        missing = [name for index, name in enumerate(names) if class_counts_by_split[split][index] == 0]
        if missing:
            raise ValueError(f"Split {split} tidak memiliki kelas: {', '.join(missing)}")

    for split in ("val", "test"):
        variants = Counter(record.original_id for record in records if record.target_split == split)
        repeated = [name for name, count in variants.items() if count > 1]
        if repeated:
            raise ValueError(f"Split {split} mengandung varian augmentasi dari frame yang sama: {repeated[:5]}")


def build_summary(records: list[Record], names: list[str], excluded: list[dict], version: str, grouping: str) -> dict:
    exclusions_by_reason = Counter(item["category"] for item in excluded)
    summary = {
        "dataset_version": version,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "classes": names,
        "split_grouping": grouping,
        "excluded_files": len(excluded),
        "excluded_by_reason": dict(exclusions_by_reason),
        "splits": {},
    }
    total_originals = len({record.original_id for record in records})
    for split in ("train", "val", "test"):
        split_records = [record for record in records if record.target_split == split]
        counts: Counter[int] = Counter()
        for record in split_records:
            counts.update(record.class_counts)
        unique_originals = len({record.original_id for record in split_records})
        summary["splits"][split] = {
            "images": len(split_records),
            "unique_originals": unique_originals,
            "original_ratio_percent": round(unique_originals / total_originals * 100, 2),
            "source_families": sorted({record.family for record in split_records}),
            "split_groups": len({record.split_group for record in split_records}),
            "boxes_by_class": {name: counts[index] for index, name in enumerate(names)},
        }
    return summary


def write_metadata(build_root: Path, records: list[Record], excluded: list[dict], summary: dict, names: list[str], source_root: Path) -> None:
    metadata_dir = build_root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "path": ".",
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": len(names),
        "names": {index: name for index, name in enumerate(names)},
        "split_grouping": summary["split_grouping"],
    }
    (build_root / "data.yaml").write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (build_root / "VERSION").write_text(f"{summary['dataset_version']}\n", encoding="utf-8")
    (metadata_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    with (metadata_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["split", "image", "label", "source_family", "original_id", "split_group", "width", "height", "image_sha256", "label_sha256"] + [f"boxes_{name}" for name in names])
        for record in sorted(records, key=lambda item: (item.target_split, item.image.name)):
            writer.writerow(
                [record.target_split, f"images/{record.target_split}/{record.image.name}", f"labels/{record.target_split}/{record.label.name}", record.family, record.original_id, record.split_group, record.width, record.height, record.image_sha256, record.label_sha256]
                + [record.class_counts.get(index, 0) for index in range(len(names))]
            )

    with (metadata_dir / "excluded.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["file", "family", "source_split", "owner_split", "category", "reason"])
        writer.writeheader()
        writer.writerows(excluded)

    checksums = [
        f"{record.image_sha256}  images/{record.target_split}/{record.image.name}"
        for record in sorted(records, key=lambda item: (item.target_split, item.image.name))
    ]
    (metadata_dir / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    (metadata_dir / "TEST_SET_LOCKED.md").write_text(
        "# Test Set Terkunci\n\nJangan gunakan split test untuk tuning hyperparameter, augmentasi, atau pemilihan checkpoint. Gunakan hanya untuk evaluasi akhir model yang sudah dipilih dari validation set.\n",
        encoding="utf-8",
    )

    split_lines = []
    for split, values in summary["splits"].items():
        split_lines.append(
            f"- **{split}**: {values['images']} file, {values['unique_originals']} frame asli ({values['original_ratio_percent']}%), "
            + ", ".join(f"{name}={values['boxes_by_class'][name]} box" for name in names)
        )
    readme = f"""# Dataset Mata Entok v{summary['dataset_version']}

Dataset canonical untuk object detection YOLO. Sumber Roboflow asli tetap dipertahankan di `{source_root.name}` dan tidak diubah.

## Split

{chr(10).join(split_lines)}

Rasio dihitung berdasarkan gambar asli sebelum augmentasi. Strategi grouping split: `{summary['split_grouping']}`. Semua varian dari gambar asli yang sama wajib berada pada split yang sama. Augmentasi yang sudah ada hanya dipertahankan pada train; validation dan test masing-masing berisi satu file per gambar asli.

## Kelas

{chr(10).join(f'- `{index}`: `{name}`' for index, name in enumerate(names))}

## Aturan

- Jangan melakukan augmentasi acak pada validation atau test.
- Jangan memindahkan frame dari satu sumber ke split lain.
- Jangan memasukkan gambar positif tanpa label sebagai background.
- Jalankan `dataset_preflight.py` sebelum training.
- Test set dikunci dan hanya dipakai untuk evaluasi akhir.

Provenance dan lisensi mengikuti ekspor Roboflow sumber (CC BY 4.0). Detail per file, checksum, dan file yang dikeluarkan tersedia di folder `metadata`.
"""
    (build_root / "README.md").write_text(readme, encoding="utf-8")


def prepare(source_root: Path, destination: Path, version: str, grouping: str = "source_family", exclude_empty_labels: bool = False) -> dict:
    source_root = source_root.resolve()
    destination = destination.resolve()
    build_root = destination.with_name(f"{destination.name}.building")
    if destination.exists() or build_root.exists():
        raise FileExistsError(f"Target sudah ada; hapus/arsipkan secara eksplisit sebelum membangun ulang: {destination}")

    names = read_names(source_root)
    raw_records, excluded = load_source_records(source_root, names, grouping, exclude_empty_labels)
    records, split_excluded = select_without_source_leakage(raw_records)
    excluded.extend(split_excluded)
    records = remove_exact_duplicates(records, excluded)
    validate_selection(records, names)

    try:
        for split in ("train", "val", "test"):
            (build_root / "images" / split).mkdir(parents=True, exist_ok=True)
            (build_root / "labels" / split).mkdir(parents=True, exist_ok=True)
        for record in records:
            shutil.copy2(record.image, build_root / "images" / record.target_split / record.image.name)
            shutil.copy2(record.label, build_root / "labels" / record.target_split / record.label.name)
        summary = build_summary(records, names, excluded, version, grouping)
        write_metadata(build_root, records, excluded, summary, names, source_root)
        build_root.rename(destination)
        return summary
    except Exception:
        if build_root.exists():
            shutil.rmtree(build_root)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Bangun dataset YOLO canonical tanpa source/session leakage.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--grouping", choices=("source_family", "original_id"), default="source_family")
    parser.add_argument("--exclude-empty-labels", action="store_true")
    args = parser.parse_args()
    summary = prepare(args.source, args.destination, args.version, args.grouping, args.exclude_empty_labels)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
