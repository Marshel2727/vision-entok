import argparse
import re
from collections import Counter
from pathlib import Path

import yaml


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _normalise_names(raw_names) -> list[str]:
    if isinstance(raw_names, dict):
        try:
            return [str(raw_names[index]) for index in range(len(raw_names))]
        except (KeyError, TypeError):
            return [str(value) for _, value in sorted(raw_names.items(), key=lambda item: int(item[0]))]
    return [str(name) for name in (raw_names or [])]


def _resolve_dataset_root(data: dict, yaml_path: Path) -> Path:
    raw_root = Path(str(data.get("path") or yaml_path.parent))
    if raw_root.is_absolute():
        return raw_root.resolve()
    return (yaml_path.parent / raw_root).resolve()


def _read_split_images(split_value, dataset_root: Path) -> list[Path]:
    values = split_value if isinstance(split_value, list) else [split_value]
    images: list[Path] = []

    for raw_value in values:
        split_path = Path(str(raw_value))
        if not split_path.is_absolute():
            split_path = dataset_root / split_path
        split_path = split_path.resolve()

        if split_path.suffix.lower() == ".txt":
            if not split_path.is_file():
                raise FileNotFoundError(f"Manifest split tidak ditemukan: {split_path}")
            for raw_line in split_path.read_text(encoding="utf-8-sig").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                image_path = Path(line)
                if not image_path.is_absolute():
                    image_path = split_path.parent / image_path
                images.append(image_path.resolve())
        elif split_path.is_dir():
            images.extend(
                path.resolve()
                for path in sorted(split_path.rglob("*"))
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
            )
        else:
            raise FileNotFoundError(f"Path split tidak ditemukan: {split_path}")

    return images


def _label_path_for(image_path: Path) -> Path:
    if image_path.parent.name.lower() == "images":
        return image_path.parent.parent / "labels" / f"{image_path.stem}.txt"
    if image_path.parent.parent.name.lower() == "images":
        dataset_root = image_path.parent.parent.parent
        return dataset_root / "labels" / image_path.parent.name / f"{image_path.stem}.txt"
    raise ValueError(f"Path gambar bukan struktur YOLO yang didukung: {image_path}")


def _source_family(image_path: Path) -> str:
    original_stem = image_path.stem.split(".rf.", 1)[0]
    return re.sub(r"[-_]\d+_(?:jpg|jpeg|png)$", "", original_stem, flags=re.IGNORECASE)


def _split_group(image_path: Path, grouping: str) -> str:
    original_stem = image_path.stem.split(".rf.", 1)[0]
    return original_stem if grouping == "original_id" else _source_family(image_path)


def validate_dataset_config(
    data_yaml: str | Path,
    expected_names: list[str] | None = None,
) -> dict[str, dict]:
    yaml_path = Path(data_yaml).resolve()
    if not yaml_path.is_file():
        raise FileNotFoundError(f"data.yaml tidak ditemukan: {yaml_path}")

    with yaml_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    names = _normalise_names(data.get("names"))
    if not names:
        raise ValueError(f"Daftar kelas kosong di {yaml_path}")
    if expected_names is not None and names != expected_names:
        raise ValueError(
            f"Urutan kelas harus {expected_names}, tetapi ditemukan {names} di {yaml_path}"
        )

    dataset_root = _resolve_dataset_root(data, yaml_path)
    grouping = str(data.get("split_grouping") or "source_family")
    allow_empty_labels = bool(data.get("allow_empty_labels", False))
    if grouping not in {"source_family", "original_id"}:
        raise ValueError(f"split_grouping tidak didukung: {grouping}")
    errors: list[str] = []
    seen_images: dict[Path, str] = {}
    families_by_split: dict[str, set[str]] = {}
    summary: dict[str, dict] = {}

    for split in ("train", "val", "test"):
        if not data.get(split):
            errors.append(f"Split '{split}' tidak didefinisikan")
            continue

        images = _read_split_images(data[split], dataset_root)
        families_by_split[split] = set()
        class_counts: Counter[int] = Counter()

        if not images:
            errors.append(f"Split '{split}' kosong")

        for image_path in images:
            if image_path in seen_images:
                errors.append(
                    f"Gambar muncul di dua split: {image_path} ({seen_images[image_path]} dan {split})"
                )
            else:
                seen_images[image_path] = split

            if not image_path.is_file():
                errors.append(f"Gambar tidak ditemukan: {image_path}")
                continue

            families_by_split[split].add(_split_group(image_path, grouping))
            label_path = _label_path_for(image_path)
            if not label_path.is_file():
                errors.append(f"Label tidak ditemukan: {label_path}")
                continue

            lines = [
                line.strip()
                for line in label_path.read_text(encoding="utf-8-sig").splitlines()
                if line.strip()
            ]
            if not lines:
                if not allow_empty_labels:
                    errors.append(f"Label kosong tidak diizinkan untuk training: {label_path}")
                continue

            for line_number, line in enumerate(lines, start=1):
                parts = line.split()
                location = f"{label_path}:{line_number}"
                if len(parts) != 5:
                    errors.append(f"Format label harus 5 kolom: {location}")
                    continue
                try:
                    class_id = int(parts[0])
                    x_center, y_center, width, height = map(float, parts[1:])
                except ValueError:
                    errors.append(f"Nilai label bukan angka valid: {location}")
                    continue

                if class_id not in range(len(names)):
                    errors.append(f"Class ID di luar rentang: {location}")
                    continue
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
                    errors.append(f"Bounding box di luar batas normalisasi: {location}")
                    continue

                class_counts[class_id] += 1

        for class_id, class_name in enumerate(names):
            if class_counts[class_id] == 0:
                errors.append(f"Split '{split}' tidak memiliki kelas '{class_name}'")

        summary[split] = {
            "images": len(images),
            "families": len(families_by_split[split]),
            "class_boxes": {
                class_name: class_counts[class_id]
                for class_id, class_name in enumerate(names)
            },
        }

    split_names = list(families_by_split)
    for index, left in enumerate(split_names):
        for right in split_names[index + 1 :]:
            overlap = sorted(families_by_split[left] & families_by_split[right])
            if overlap:
                errors.append(
                    f"Kebocoran sumber antara {left} dan {right}: {', '.join(overlap)}"
                )

    if errors:
        preview = "\n".join(f"- {error}" for error in errors[:25])
        remaining = len(errors) - 25
        suffix = f"\n- ... dan {remaining} masalah lain" if remaining > 0 else ""
        raise ValueError(f"Preflight dataset GAGAL ({len(errors)} masalah):\n{preview}{suffix}")

    print("Preflight dataset LULUS")
    for split, values in summary.items():
        class_summary = ", ".join(
            f"{class_name}={count}"
            for class_name, count in values["class_boxes"].items()
        )
        print(
            f"- {split}: {values['images']} gambar, {values['families']} sumber, "
            f"{class_summary}"
        )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Validasi dataset YOLO sebelum training.")
    parser.add_argument("data", help="Path ke data.yaml yang akan divalidasi.")
    parser.add_argument(
        "--expected-names",
        nargs="+",
        default=None,
        help="Urutan nama kelas yang diwajibkan, contoh: abnormal normal.",
    )
    args = parser.parse_args()
    validate_dataset_config(args.data, expected_names=args.expected_names)


if __name__ == "__main__":
    main()
