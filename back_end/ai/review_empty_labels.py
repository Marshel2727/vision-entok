import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def build_montage(source_root: Path, output: Path) -> None:
    pairs: list[tuple[Path, Path]] = []
    for split in ("train", "valid", "test"):
        label_dir = source_root / split / "labels"
        image_dir = source_root / split / "images"
        if not label_dir.is_dir():
            continue
        for label in sorted(label_dir.glob("*.txt")):
            if label.read_text(encoding="utf-8-sig").strip():
                continue
            matches = [path for path in image_dir.glob(f"{label.stem}.*") if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}]
            if len(matches) != 1:
                raise ValueError(f"Pasangan gambar label kosong tidak unik: {label}")
            pairs.append((matches[0], label))

    columns = 4
    cell_width, cell_height, title_height = 320, 220, 30
    rows = max(1, (len(pairs) + columns - 1) // columns)
    canvas = Image.new("RGB", (columns * cell_width, rows * (cell_height + title_height)), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, (image_path, _) in enumerate(pairs):
        row, column = divmod(index, columns)
        image = Image.open(image_path).convert("RGB")
        preview = ImageOps.contain(image, (cell_width, cell_height), Image.Resampling.LANCZOS)
        x = column * cell_width + (cell_width - preview.width) // 2
        y = row * (cell_height + title_height) + title_height + (cell_height - preview.height) // 2
        canvas.paste(preview, (x, y))
        draw.text((column * cell_width + 5, row * (cell_height + title_height) + 7), image_path.name[:43], fill=(15, 23, 42), font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=92, optimize=True)
    print(f"label_kosong={len(pairs)} montage={output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Buat montage gambar dengan label YOLO kosong untuk review manual.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build_montage(args.source.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
