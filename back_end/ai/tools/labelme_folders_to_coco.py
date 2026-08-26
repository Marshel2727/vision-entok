from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
DEFAULT_OUTPUT_NAME = "_annotations.coco.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Konversi setiap subfolder LabelMe/X-AnyLabeling menjadi satu COCO JSON "
            "yang dapat diimpor ke Roboflow."
        )
    )
    parser.add_argument(
        "root",
        type=Path,
        help="Folder induk yang berisi subfolder dataset, misalnya dataset/images.",
    )
    parser.add_argument(
        "--output-name",
        default=DEFAULT_OUTPUT_NAME,
        help=f"Nama COCO JSON di setiap subfolder (default: {DEFAULT_OUTPUT_NAME}).",
    )
    parser.add_argument(
        "--qa-output",
        type=Path,
        default=None,
        help="Opsional: simpan montage pemeriksaan bounding box dari setiap folder.",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help=(
            "Masukkan JSON tanpa shape sebagai negative image. Default: dikecualikan "
            "agar gambar yang belum selesai dilabeli tidak dianggap background."
        ),
    )
    return parser.parse_args()


def load_labelme(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict) or "shapes" not in data:
        raise ValueError(f"Bukan JSON LabelMe/X-AnyLabeling: {path}")
    if not isinstance(data["shapes"], list):
        raise ValueError(f"Field shapes harus berupa list: {path}")
    return data


def labelme_files(folder: Path, output_name: str) -> list[Path]:
    return sorted(
        path
        for path in folder.glob("*.json")
        if path.name.lower() != output_name.lower()
    )


def image_index(folder: Path) -> tuple[dict[str, Path], dict[str, list[Path]]]:
    by_name: dict[str, Path] = {}
    by_stem: dict[str, list[Path]] = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        by_name[path.name.lower()] = path
        by_stem.setdefault(path.stem.lower(), []).append(path)
    return by_name, by_stem


def resolve_image(
    folder: Path,
    label_path: Path,
    data: dict[str, Any],
    by_name: dict[str, Path],
    by_stem: dict[str, list[Path]],
) -> Path:
    image_path_value = str(data.get("imagePath") or "").replace("\\", "/")
    image_name = Path(image_path_value).name
    if image_name and image_name.lower() in by_name:
        return by_name[image_name.lower()]

    candidates = by_stem.get(label_path.stem.lower(), [])
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise ValueError(f"Pasangan gambar ambigu untuk {label_path.name}: {names}")
    raise FileNotFoundError(
        f"Gambar pasangan tidak ditemukan untuk {label_path.name} di {folder}"
    )


def rectangle_bbox(
    shape: dict[str, Any], width: int, height: int, source: Path
) -> tuple[float, float, float, float]:
    shape_type = str(shape.get("shape_type") or "rectangle").lower()
    if shape_type != "rectangle":
        raise ValueError(
            f"Shape {shape_type!r} belum didukung; diperlukan rectangle: {source}"
        )

    points = shape.get("points")
    if not isinstance(points, list) or len(points) < 2:
        raise ValueError(f"Rectangle tidak memiliki dua titik: {source}")

    try:
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(f"Koordinat rectangle tidak valid: {source}") from exc

    x1 = max(0.0, min(float(width), min(xs)))
    y1 = max(0.0, min(float(height), min(ys)))
    x2 = max(0.0, min(float(width), max(xs)))
    y2 = max(0.0, min(float(height), max(ys)))
    box_width = x2 - x1
    box_height = y2 - y1
    if box_width <= 0 or box_height <= 0:
        raise ValueError(f"Bounding box kosong/terbalik: {source}")
    return x1, y1, box_width, box_height


def collect_categories(folders: list[Path], output_name: str) -> list[str]:
    labels: set[str] = set()
    for folder in folders:
        for label_path in labelme_files(folder, output_name):
            data = load_labelme(label_path)
            for shape in data["shapes"]:
                label = str(shape.get("label") or "").strip()
                if not label:
                    raise ValueError(f"Shape tanpa label: {label_path}")
                labels.add(label)
    if not labels:
        raise ValueError("Tidak ada kategori anotasi yang ditemukan.")
    return sorted(labels, key=str.casefold)


def convert_folder(
    folder: Path,
    output_name: str,
    category_ids: dict[str, int],
    include_empty: bool,
) -> dict[str, Any]:
    by_name, by_stem = image_index(folder)
    label_paths = labelme_files(folder, output_name)
    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    used_images: set[Path] = set()
    paired_images: set[Path] = set()
    included_empty_images = 0
    excluded_empty_images = 0
    annotation_id = 1
    image_id = 1

    for label_path in label_paths:
        data = load_labelme(label_path)
        image_path = resolve_image(folder, label_path, data, by_name, by_stem)
        if image_path in paired_images:
            raise ValueError(f"Gambar dipakai oleh lebih dari satu JSON: {image_path}")
        paired_images.add(image_path)

        shapes = data["shapes"]
        if not shapes and not include_empty:
            excluded_empty_images += 1
            continue
        if not shapes:
            included_empty_images += 1
        used_images.add(image_path)

        with Image.open(image_path) as image:
            width, height = image.size

        json_width = data.get("imageWidth")
        json_height = data.get("imageHeight")
        if json_width and json_height:
            if int(json_width) != width or int(json_height) != height:
                raise ValueError(
                    "Ukuran gambar berbeda dengan JSON: "
                    f"{image_path.name} actual={width}x{height}, "
                    f"json={json_width}x{json_height}"
                )

        images.append(
            {
                "id": image_id,
                "file_name": image_path.name,
                "width": width,
                "height": height,
            }
        )

        for shape in shapes:
            label = str(shape.get("label") or "").strip()
            if label not in category_ids:
                raise ValueError(f"Kategori tidak terdaftar {label!r}: {label_path}")
            x, y, box_width, box_height = rectangle_bbox(
                shape, width, height, label_path
            )
            annotations.append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": category_ids[label],
                    "bbox": [x, y, box_width, box_height],
                    "area": box_width * box_height,
                    "segmentation": [],
                    "iscrowd": 0,
                }
            )
            annotation_id += 1
        image_id += 1

    categories = [
        {"id": category_id, "name": name, "supercategory": "none"}
        for name, category_id in sorted(category_ids.items(), key=lambda item: item[1])
    ]
    coco = {
        "info": {
            "description": f"Deteksi mata entok - {folder.name}",
            "version": "1.0",
            "year": datetime.now(timezone.utc).year,
            "date_created": datetime.now(timezone.utc).isoformat(),
        },
        "licenses": [],
        "images": images,
        "annotations": annotations,
        "categories": categories,
    }

    output_path = folder / output_name
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(coco, file, ensure_ascii=False, indent=2)
        file.write("\n")

    all_image_count = len(by_name)
    return {
        "folder": folder.name,
        "output": output_path,
        "images": len(images),
        "annotations": len(annotations),
        "included_empty_images": included_empty_images,
        "excluded_empty_images": excluded_empty_images,
        "excluded_unlabeled": all_image_count - len(paired_images),
        "labels": Counter(
            category["name"]
            for annotation in annotations
            for category in categories
            if category["id"] == annotation["category_id"]
        ),
    }


def validate_coco(path: Path) -> None:
    with path.open("r", encoding="utf-8") as file:
        coco = json.load(file)

    image_ids = {image["id"] for image in coco["images"]}
    category_ids = {category["id"] for category in coco["categories"]}
    annotation_ids: set[int] = set()
    images_by_id = {image["id"]: image for image in coco["images"]}

    if len(image_ids) != len(coco["images"]):
        raise ValueError(f"Image ID duplikat: {path}")

    for image in coco["images"]:
        if not (path.parent / image["file_name"]).is_file():
            raise FileNotFoundError(f"Referensi gambar tidak ada: {image['file_name']}")

    for annotation in coco["annotations"]:
        annotation_id = annotation["id"]
        if annotation_id in annotation_ids:
            raise ValueError(f"Annotation ID duplikat: {path}")
        annotation_ids.add(annotation_id)
        if annotation["image_id"] not in image_ids:
            raise ValueError(f"image_id tidak dikenal: {path}")
        if annotation["category_id"] not in category_ids:
            raise ValueError(f"category_id tidak dikenal: {path}")

        image = images_by_id[annotation["image_id"]]
        x, y, width, height = annotation["bbox"]
        if width <= 0 or height <= 0:
            raise ValueError(f"BBox tidak positif: {path}")
        if x < 0 or y < 0 or x + width > image["width"] + 1e-6:
            raise ValueError(f"BBox melewati lebar gambar: {path}")
        if y + height > image["height"] + 1e-6:
            raise ValueError(f"BBox melewati tinggi gambar: {path}")


def render_qa(summaries: list[dict[str, Any]], output_path: Path) -> None:
    tile_width, tile_height = 640, 360
    columns = 2
    rows = (len(summaries) + columns - 1) // columns
    canvas = Image.new("RGB", (tile_width * columns, tile_height * rows), "black")
    canvas_draw = ImageDraw.Draw(canvas)

    for index, summary in enumerate(summaries):
        with summary["output"].open("r", encoding="utf-8") as file:
            coco = json.load(file)

        annotations_by_image: dict[int, list[dict[str, Any]]] = {}
        for annotation in coco["annotations"]:
            annotations_by_image.setdefault(annotation["image_id"], []).append(
                annotation
            )

        selected = max(
            coco["images"],
            key=lambda image: len(annotations_by_image.get(image["id"], [])),
        )
        image_path = summary["output"].parent / selected["file_name"]
        with Image.open(image_path) as image_file:
            image = image_file.convert("RGB")

        draw = ImageDraw.Draw(image)
        selected_annotations = annotations_by_image.get(selected["id"], [])
        for annotation in selected_annotations:
            x, y, width, height = annotation["bbox"]
            draw.rectangle(
                (x, y, x + width, y + height),
                outline=(255, 40, 40),
                width=max(2, round(min(image.size) / 300)),
            )

        image.thumbnail((tile_width, tile_height - 28), Image.Resampling.LANCZOS)
        column = index % columns
        row = index // columns
        tile_x = column * tile_width
        tile_y = row * tile_height
        paste_x = tile_x + (tile_width - image.width) // 2
        paste_y = tile_y + 28 + (tile_height - 28 - image.height) // 2
        canvas.paste(image, (paste_x, paste_y))
        canvas_draw.text(
            (tile_x + 8, tile_y + 8),
            f"{summary['folder']} | boxes={len(selected_annotations)} | {selected['file_name']}",
            fill=(255, 255, 0),
        )

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, quality=92)
    print(f"QA montage: {output_path}")


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Folder dataset tidak ditemukan: {root}")

    folders = sorted(
        (path for path in root.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    )
    if not folders:
        raise ValueError(f"Tidak ada subfolder dataset di: {root}")

    category_names = collect_categories(folders, args.output_name)
    category_ids = {name: index for index, name in enumerate(category_names, start=1)}
    print("Kategori COCO:", ", ".join(f"{id_}={name}" for name, id_ in category_ids.items()))

    summaries = []
    for folder in folders:
        summary = convert_folder(
            folder, args.output_name, category_ids, include_empty=args.include_empty
        )
        validate_coco(summary["output"])
        summaries.append(summary)
        print(
            f"{summary['folder']}: images={summary['images']}, "
            f"annotations={summary['annotations']}, "
            f"included_empty={summary['included_empty_images']}, "
            f"excluded_empty={summary['excluded_empty_images']}, "
            f"excluded_unlabeled={summary['excluded_unlabeled']}"
        )
        print(f"  OK: {summary['output']}")

    print(
        "TOTAL:",
        f"folders={len(summaries)},",
        f"images={sum(item['images'] for item in summaries)},",
        f"annotations={sum(item['annotations'] for item in summaries)},",
        f"excluded_unlabeled={sum(item['excluded_unlabeled'] for item in summaries)}",
    )
    if args.qa_output is not None:
        render_qa(summaries, args.qa_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
