from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import yaml


AI_DIR = Path(__file__).resolve().parents[1]
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

import prepare_dataset as base


SPLITS = ("train", "val", "test")


def normalized_source_group(image_path: Path) -> str:
    """Satukan salinan sumber WhatsApp, misalnya `(1)` dan `(2)`."""
    family = base.source_family(image_path)
    return re.sub(
        r"-\d+-_(mp4|jpe?g|png)$",
        r"_\1",
        family,
        flags=re.IGNORECASE,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bangun dataset YOLO canonical dengan split ulang berbasis sumber/sesi. "
            "Augmentasi dipertahankan hanya di train."
        )
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.80)
    parser.add_argument("--val-ratio", type=float, default=0.10)
    parser.add_argument("--test-ratio", type=float, default=0.10)
    return parser.parse_args()


def stable_key(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode("utf-8")).hexdigest()


def choose_eval_groups(
    candidates: dict[str, int],
    target: int,
    seed: int,
    split_name: str,
    min_groups: int = 3,
    max_groups: int = 8,
) -> set[str]:
    ordered = sorted(
        candidates.items(),
        key=lambda item: stable_key(seed, f"{split_name}:{item[0]}"),
    )
    max_total = target + max(candidates.values(), default=0)
    states: dict[tuple[int, int], tuple[str, ...]] = {(0, 0): ()}

    for group_name, weight in ordered:
        updates: dict[tuple[int, int], tuple[str, ...]] = {}
        for (total, count), selected in list(states.items()):
            if count >= max_groups or total + weight > max_total:
                continue
            key = (total + weight, count + 1)
            candidate = (*selected, group_name)
            current = states.get(key) or updates.get(key)
            if current is None or stable_key(seed, "|".join(candidate)) < stable_key(
                seed, "|".join(current)
            ):
                updates[key] = candidate
        states.update(updates)

    eligible = [
        (total, count, selected)
        for (total, count), selected in states.items()
        if min_groups <= count <= max_groups
    ]
    if not eligible:
        raise ValueError(f"Tidak dapat memilih kelompok untuk split {split_name}")

    total, count, selected = min(
        eligible,
        key=lambda item: (
            abs(item[0] - target),
            abs(item[1] - 5),
            stable_key(seed, f"{split_name}:{'|'.join(item[2])}"),
        ),
    )
    print(
        f"{split_name}: target_originals={target}, "
        f"selected_originals={total}, groups={count}"
    )
    return set(selected)


def assign_source_groups(
    raw_records: list[dict],
    ratios: dict[str, float],
    seed: int,
) -> dict[str, str]:
    originals_by_group: dict[str, set[str]] = defaultdict(set)
    for record in raw_records:
        originals_by_group[record["split_group"]].add(record["original_id"])

    weights = {
        group: len(originals) for group, originals in originals_by_group.items()
    }
    total_originals = len({record["original_id"] for record in raw_records})
    remaining = dict(weights)

    test_groups = choose_eval_groups(
        remaining,
        target=max(1, round(total_originals * ratios["test"])),
        seed=seed,
        split_name="test",
    )
    for group in test_groups:
        remaining.pop(group)

    val_groups = choose_eval_groups(
        remaining,
        target=max(1, round(total_originals * ratios["val"])),
        seed=seed,
        split_name="val",
    )

    assignments = {group: "train" for group in weights}
    assignments.update({group: "test" for group in test_groups})
    assignments.update({group: "val" for group in val_groups})
    return assignments


def select_eval_variant(records: list[dict], target_split: str) -> dict:
    source_priority = {
        target_split: 0,
        "val" if target_split == "test" else "test": 1,
        "train": 2,
    }
    return min(
        records,
        key=lambda record: (
            source_priority.get(record["target_split"], 3),
            record["image"].name,
        ),
    )


def resplit_records(
    raw_records: list[dict],
    assignments: dict[str, str],
    excluded: list[dict],
) -> list[base.Record]:
    by_group: dict[str, list[dict]] = defaultdict(list)
    for record in raw_records:
        by_group[record["split_group"]].append(record)

    selected: list[base.Record] = []
    for group_name, group_records in sorted(by_group.items()):
        target_split = assignments[group_name]
        if target_split == "train":
            kept_records = group_records
        else:
            by_original: dict[str, list[dict]] = defaultdict(list)
            for record in group_records:
                by_original[record["original_id"]].append(record)
            kept_records = [
                select_eval_variant(variants, target_split)
                for _, variants in sorted(by_original.items())
            ]
            kept_ids = {id(record) for record in kept_records}
            for record in group_records:
                if id(record) in kept_ids:
                    continue
                excluded.append(
                    {
                        "file": record["image"].name,
                        "family": record["family"],
                        "source_split": record["target_split"],
                        "owner_split": target_split,
                        "category": "eval_extra_variant",
                        "reason": (
                            "varian tambahan dikeluarkan; validation/test hanya "
                            "menyimpan satu gambar per frame asli"
                        ),
                    }
                )

        for raw in kept_records:
            selected.append(base.Record(**{**raw, "target_split": target_split}))
    return selected


def write_group_assignments(
    destination: Path,
    assignments: dict[str, str],
    raw_records: list[dict],
) -> None:
    originals_by_group: dict[str, set[str]] = defaultdict(set)
    images_by_group: dict[str, int] = defaultdict(int)
    for record in raw_records:
        originals_by_group[record["split_group"]].add(record["original_id"])
        images_by_group[record["split_group"]] += 1

    output = destination / "metadata" / "group_assignments.csv"
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["source_group", "split", "unique_originals", "source_images"])
        for group_name, split in sorted(assignments.items()):
            writer.writerow(
                [
                    group_name,
                    split,
                    len(originals_by_group[group_name]),
                    images_by_group[group_name],
                ]
            )


def prepare(
    source: Path,
    destination: Path,
    version: str,
    ratios: dict[str, float],
    seed: int,
) -> dict:
    source = source.resolve()
    destination = destination.resolve()
    build_root = destination.with_name(f"{destination.name}.building")
    if destination.exists() or build_root.exists():
        raise FileExistsError(
            "Target sudah ada; hapus/arsipkan secara eksplisit sebelum membangun ulang: "
            f"{destination}"
        )

    names = base.read_names(source)
    raw_records, excluded = base.load_source_records(
        source,
        names,
        grouping="source_family",
        exclude_empty_labels=True,
    )
    for record in raw_records:
        record["split_group"] = normalized_source_group(record["image"])
    assignments = assign_source_groups(raw_records, ratios, seed)
    records = resplit_records(raw_records, assignments, excluded)
    records = base.remove_exact_duplicates(records, excluded)
    base.validate_selection(records, names)

    try:
        for split in SPLITS:
            (build_root / "images" / split).mkdir(parents=True, exist_ok=True)
            (build_root / "labels" / split).mkdir(parents=True, exist_ok=True)
        for record in records:
            shutil.copy2(
                record.image,
                build_root / "images" / record.target_split / record.image.name,
            )
            shutil.copy2(
                record.label,
                build_root / "labels" / record.target_split / record.label.name,
            )

        summary = base.build_summary(
            records,
            names,
            excluded,
            version=version,
            grouping="source_family",
        )
        summary.update(
            {
                "split_strategy": "deterministic_source_group_resplit",
                "source_group_normalization": "whatsapp_copy_suffix",
                "seed": seed,
                "requested_ratios": ratios,
                "source_dataset": str(source),
            }
        )
        base.write_metadata(build_root, records, excluded, summary, names, source)
        ultralytics_data = {
            "path": destination.as_posix(),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "nc": len(names),
            "names": {index: name for index, name in enumerate(names)},
            "split_grouping": summary["split_grouping"],
        }
        (build_root / "data.yaml").write_text(
            yaml.safe_dump(ultralytics_data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        write_group_assignments(build_root, assignments, raw_records)
        build_root.rename(destination)
        return summary
    except Exception:
        if build_root.exists():
            shutil.rmtree(build_root)
        raise


def main() -> int:
    args = parse_args()
    ratios = {
        "train": args.train_ratio,
        "val": args.val_ratio,
        "test": args.test_ratio,
    }
    if any(value <= 0 for value in ratios.values()):
        raise ValueError("Semua rasio split harus lebih besar dari 0")
    total = sum(ratios.values())
    ratios = {name: value / total for name, value in ratios.items()}
    summary = prepare(
        args.source,
        args.destination,
        args.version,
        ratios,
        args.seed,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
