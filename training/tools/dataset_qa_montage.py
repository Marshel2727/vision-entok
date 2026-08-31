import argparse
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont, ImageOps


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
COLORS = [(225, 29, 72), (22, 163, 74), (37, 99, 235), (234, 88, 12)]


def choose_samples(paths: list[Path], count: int) -> list[Path]:
    if len(paths) <= count:
        return paths
    if count == 1:
        return [paths[len(paths) // 2]]
    indexes = [round(index * (len(paths) - 1) / (count - 1)) for index in range(count)]
    return [paths[index] for index in indexes]


def annotate(image_path: Path, label_path: Path, names: list[str]) -> Image.Image:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    line_width = max(2, round(min(image.size) / 240))
    for line in label_path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        class_id, x_center, y_center, width, height = line.split()
        class_index = int(class_id)
        x_center, y_center, width, height = map(float, (x_center, y_center, width, height))
        x1 = (x_center - width / 2) * image.width
        y1 = (y_center - height / 2) * image.height
        x2 = (x_center + width / 2) * image.width
        y2 = (y_center + height / 2) * image.height
        color = COLORS[class_index % len(COLORS)]
        draw.rectangle((x1, y1, x2, y2), outline=color, width=line_width)
        label = names[class_index]
        text_box = draw.textbbox((x1, y1), label, font=font)
        draw.rectangle(text_box, fill=color)
        draw.text((x1, y1), label, fill="white", font=font)
    return image


def build_montage(dataset_root: Path, output: Path, samples_per_split: int = 4) -> None:
    with (dataset_root / "data.yaml").open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    raw_names = config.get("names") or {}
    names = [str(raw_names[index]) for index in range(len(raw_names))] if isinstance(raw_names, dict) else list(raw_names)

    cell_width, cell_height, header_height = 320, 220, 28
    splits = ("train", "val", "test")
    canvas = Image.new("RGB", (cell_width * samples_per_split, (cell_height + header_height) * len(splits)), "white")
    canvas_draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()

    for row, split in enumerate(splits):
        images = sorted(path for path in (dataset_root / "images" / split).iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
        samples = choose_samples(images, samples_per_split)
        for column, image_path in enumerate(samples):
            label_path = dataset_root / "labels" / split / f"{image_path.stem}.txt"
            annotated = annotate(image_path, label_path, names)
            preview = ImageOps.contain(annotated, (cell_width, cell_height), Image.Resampling.LANCZOS)
            x = column * cell_width + (cell_width - preview.width) // 2
            y = row * (cell_height + header_height) + header_height + (cell_height - preview.height) // 2
            canvas.paste(preview, (x, y))
            title = f"{split} | {image_path.name[:38]}"
            canvas_draw.text((column * cell_width + 6, row * (cell_height + header_height) + 7), title, fill=(15, 23, 42), font=font)

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=92, optimize=True)
    print(f"Montage QA tersimpan: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Buat montage visual QA untuk dataset YOLO canonical.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--samples-per-split", type=int, default=4)
    args = parser.parse_args()
    dataset_root = args.dataset.resolve()
    output = args.output.resolve() if args.output else dataset_root / "metadata" / "qa_montage.jpg"
    build_montage(dataset_root, output, args.samples_per_split)


if __name__ == "__main__":
    main()
