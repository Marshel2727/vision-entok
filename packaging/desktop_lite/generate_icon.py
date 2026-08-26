from pathlib import Path

from PIL import Image, ImageDraw


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "assets" / "entok_vision_lite.ico"
PREVIEW = HERE / "assets" / "entok_vision_lite.png"


def main() -> None:
    size = 256
    image = Image.new("RGBA", (size, size), (15, 23, 42, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (4, 4, size - 4, size - 4),
        radius=52,
        fill=(15, 118, 110, 255),
        outline=(34, 211, 238, 255),
        width=7,
    )
    draw.polygon(
        [(45, 156), (72, 103), (112, 77), (165, 70), (211, 94), (169, 112),
         (207, 138), (176, 166), (130, 185), (78, 185)],
        fill=(248, 250, 252, 255),
    )
    draw.polygon([(164, 109), (226, 128), (164, 148)], fill=(251, 146, 60, 255))
    draw.ellipse((99, 88, 149, 138), fill=(15, 23, 42, 255))
    draw.ellipse((109, 98, 139, 128), fill=(34, 211, 238, 255))
    draw.ellipse((123, 102, 134, 113), fill=(255, 255, 255, 255))
    draw.arc((48, 127, 194, 194), 18, 160, fill=(34, 211, 238, 255), width=9)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW, format="PNG")
    image.save(
        OUTPUT,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
