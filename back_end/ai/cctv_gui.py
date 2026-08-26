from __future__ import annotations

import argparse
import os
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
from dotenv import load_dotenv
from ultralytics import YOLO

try:
    from .configs.config_loader import load_yaml_config, resolve_config_path
    from .frame_sources import create_frame_source, ensure_dir, redact_source
    from .vigi_ptz import VigiPTZ, settings_from_source
except ImportError:
    from configs.config_loader import load_yaml_config, resolve_config_path
    from frame_sources import create_frame_source, ensure_dir, redact_source
    from vigi_ptz import VigiPTZ, settings_from_source


AI_DIR = Path(__file__).resolve().parent
BACKEND_DIR = AI_DIR.parent
DEFAULT_CONFIG = AI_DIR / "configs" / "cctv_gui.yaml"
SETTINGS_EXIT_CODE = 10


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GUI desktop deteksi mata entok dari CCTV RTSP."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--model", default=None, help="Path model YOLO .pt.")
    parser.add_argument(
        "--source",
        default=None,
        help="Override sumber video. Lebih aman simpan URL RTSP di CCTV_RTSP_URL.",
    )
    parser.add_argument("--conf", type=float, default=None)
    parser.add_argument("--imgsz", type=int, default=None)
    parser.add_argument("--device", default=None, help="auto, cpu, atau nomor GPU seperti 0.")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validasi config, model, dan koneksi kamera tanpa membuka GUI.",
    )
    return parser.parse_args(argv)


def get_value(args: argparse.Namespace, config: dict[str, Any], key: str, default: Any):
    value = getattr(args, key, None)
    return value if value is not None else config.get(key, default)


def resolve_source(args: argparse.Namespace, config: dict[str, Any]) -> str:
    if args.source is not None:
        source = str(args.source).strip()
    else:
        source_env = str(config.get("source_env", "CCTV_RTSP_URL")).strip()
        source = os.getenv(source_env, "").strip()
        if not source and config.get("source") is not None:
            source = str(config["source"]).strip()

    if not source:
        raise ValueError(
            "URL CCTV belum diatur. Isi CCTV_RTSP_URL pada back_end/.env."
        )
    return source


def resolve_model(args: argparse.Namespace, config: dict[str, Any]) -> Path:
    model_value = get_value(args, config, "model", "models/best.pt")
    return resolve_model_file(model_value, config)


def resolve_model_file(model_value: str | Path, config: dict[str, Any]) -> Path:
    model_path = resolve_config_path(str(model_value), config)
    if not model_path.is_file():
        raise FileNotFoundError(f"Model tidak ditemukan: {model_path}")
    return model_path


def build_model_choices(
    args: argparse.Namespace,
    config: dict[str, Any],
    initial_model_path: Path,
) -> list[tuple[str, Path]]:
    choices: list[tuple[str, Path]] = []
    seen: set[Path] = set()

    def add_choice(name: str, path: Path) -> None:
        resolved = path.resolve()
        if resolved not in seen:
            choices.append((name, resolved))
            seen.add(resolved)

    if args.model is not None:
        add_choice(f"Custom: {initial_model_path.stem}", initial_model_path)

    configured_models = config.get("models", [])
    if isinstance(configured_models, list):
        for index, item in enumerate(configured_models, start=1):
            if not isinstance(item, dict) or not item.get("path"):
                continue
            path = resolve_model_file(str(item["path"]), config)
            name = str(item.get("name") or f"Model {index}")
            add_choice(name, path)

    add_choice(initial_model_path.stem, initial_model_path)
    return choices


def model_has_class(model: YOLO, class_name: str) -> bool:
    names = getattr(model, "names", {})
    values = names.values() if isinstance(names, dict) else names
    return any(str(name).lower() == class_name.lower() for name in values)


def choose_custom_model(initial_dir: Path) -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="Pilih model YOLO",
            initialdir=str(initial_dir),
            filetypes=[
                ("Model YOLO", "*.pt *.onnx *.engine"),
                ("PyTorch", "*.pt"),
                ("ONNX", "*.onnx"),
                ("TensorRT", "*.engine"),
                ("Semua file", "*.*"),
            ],
        )
        root.destroy()
    except Exception as exc:
        print(f"File picker tidak dapat dibuka: {exc}")
        return None

    return Path(selected).resolve() if selected else None


def get_held_ptz_direction(window_name: str) -> tuple[bool, str | None]:
    """Baca tombol WASD yang sedang ditahan pada jendela GUI aktif di Windows."""
    if os.name != "nt":
        return False, None

    import ctypes

    user32 = ctypes.windll.user32
    window_handle = user32.FindWindowW(None, window_name)
    if not window_handle or user32.GetForegroundWindow() != window_handle:
        return True, None

    key_map = (
        ("up", ord("W")),
        ("down", ord("S")),
        ("left", ord("A")),
        ("right", ord("D")),
    )
    for direction, key_code in key_map:
        if user32.GetAsyncKeyState(key_code) & 0x8000:
            return True, direction
    return True, None


def update_ptz_from_held_keys(
    controller: VigiPTZ | None,
    window_name: str,
) -> bool:
    held_keys_supported, direction = get_held_ptz_direction(window_name)
    if controller is None or not controller.connected or not held_keys_supported:
        return held_keys_supported

    if direction is not None:
        controller.start_move(direction)
    elif controller.current_direction is not None:
        controller.stop()
    return held_keys_supported


def initialize_ptz(
    config: dict[str, Any],
    source: str,
    window_name: str,
    window_width: int,
    window_height: int,
) -> tuple[VigiPTZ | None, str]:
    if not bool(config.get("ptz_enabled", True)):
        return None, "NONAKTIF"

    status_frame = make_status_frame(
        "Menghubungkan kontrol PTZ",
        ["Mencoba ONVIF kamera VIGI. GUI tetap dapat digunakan jika PTZ gagal."],
        width=window_width,
        height=window_height,
    )
    cv2.imshow(window_name, status_frame)
    cv2.waitKey(1)

    try:
        controller = VigiPTZ(settings_from_source(source, config))
    except ValueError as exc:
        print(f"Konfigurasi PTZ tidak valid: {exc}")
        return None, "KONFIGURASI GAGAL"

    if controller.connect():
        return controller, f"SIAP {controller.endpoint}"
    return controller, "TIDAK TERSEDIA"


def put_text(
    frame: np.ndarray,
    text: str,
    position: tuple[int, int],
    color: tuple[int, int, int],
    scale: float,
    thickness: int,
) -> None:
    cv2.putText(
        frame,
        text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (0, 0, 0),
        thickness + 3,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def draw_compact_row(
    frame: np.ndarray,
    segments: list[tuple[str, tuple[int, int, int]]],
    *,
    y: int,
    left: int,
    right: int,
    preferred_scale: float,
) -> None:
    """Gambar satu baris HUD kecil dan sesuaikan ukurannya dengan lebar frame."""
    separator = "  |  "
    prepared_segments: list[tuple[str, tuple[int, int, int]]] = []
    for index, segment in enumerate(segments):
        if index:
            prepared_segments.append((separator, (150, 150, 150)))
        prepared_segments.append(segment)

    available_width = max(1, right - left)
    natural_width = sum(
        cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 1)[0][0]
        for text, _ in prepared_segments
    )
    scale = min(preferred_scale, available_width / max(natural_width, 1))
    scale = max(0.24, scale)

    x = left
    for text, color in prepared_segments:
        cv2.putText(
            frame,
            text,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            text,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            1,
            cv2.LINE_AA,
        )
        x += cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0]


def draw_hud(
    frame: np.ndarray,
    *,
    fps: float,
    detection_count: int,
    abnormal_count: int,
    confidence: float,
    model_name: str,
    device_name: str,
    supports_abnormal: bool,
    paused: bool,
    auto_screenshot: bool,
    auto_screenshot_interval: float,
    ptz_status: str,
    ptz_direction: str | None,
) -> np.ndarray:
    height, width = frame.shape[:2]
    preferred_scale = max(0.42, min(0.62, width / 3000))
    bar_height = max(52, round(height * 0.058))
    bar_top = height - bar_height
    padding_x = max(10, round(width * 0.006))

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, bar_top), (width, height), (10, 10, 10), -1)
    cv2.addWeighted(overlay, 0.76, frame, 0.24, 0, frame)
    cv2.line(frame, (0, bar_top), (width, bar_top), (70, 70, 70), 1, cv2.LINE_AA)

    status = (
        "JEDA"
        if paused
        else (
            "MODE NORMAL ONLY"
            if not supports_abnormal
            else ("ABNORMAL TERDETEKSI" if abnormal_count else "MONITORING AKTIF")
        )
    )
    status_color = (0, 165, 255) if paused else ((0, 0, 255) if abnormal_count else (0, 255, 0))
    compact_model_name = (
        model_name if len(model_name) <= 42 else f"{model_name[:39]}..."
    )
    ptz_short = "SIAP" if ptz_status.startswith("SIAP") else ptz_status
    if ptz_direction:
        ptz_short += f" {ptz_direction.upper()}"

    first_row = [
        (f"FPS {fps:.1f}", (0, 255, 0)),
        (f"DET {detection_count}", (235, 235, 235)),
        (f"ABN {abnormal_count}", status_color),
        (f"CONF {confidence:.2f}", (0, 190, 255)),
        (f"MODEL {compact_model_name}", (255, 255, 0)),
        (f"DEVICE {device_name.upper()}", (180, 220, 255)),
        (status, status_color),
    ]
    second_row = [
        (
            f"SS {'ON' if auto_screenshot else 'OFF'}"
            + (f" {auto_screenshot_interval:.1f}s" if auto_screenshot else ""),
            (0, 255, 0) if auto_screenshot else (160, 160, 160),
        ),
        (
            f"PTZ {ptz_short}",
            (0, 255, 255) if ptz_status.startswith("SIAP") else (160, 160, 160),
        ),
        ("WASD PTZ", (220, 220, 220)),
        ("T AUTO-SS", (220, 220, 220)),
        ("C SS", (220, 220, 220)),
        ("P JEDA", (220, 220, 220)),
        ("M MODEL", (220, 220, 220)),
        ("O FILE", (220, 220, 220)),
        ("G SETTING", (220, 220, 220)),
        ("+/- CONF", (220, 220, 220)),
        ("R RECONNECT", (220, 220, 220)),
        ("Q KELUAR", (220, 220, 220)),
    ]
    draw_compact_row(
        frame,
        first_row,
        y=bar_top + round(bar_height * 0.40),
        left=padding_x,
        right=width - padding_x,
        preferred_scale=preferred_scale,
    )
    draw_compact_row(
        frame,
        second_row,
        y=bar_top + round(bar_height * 0.82),
        left=padding_x,
        right=width - padding_x,
        preferred_scale=preferred_scale * 0.90,
    )
    return frame


def make_status_frame(
    title: str,
    messages: list[str],
    *,
    width: int,
    height: int,
    error: bool = False,
) -> np.ndarray:
    frame = np.full((height, width, 3), (25, 25, 25), dtype=np.uint8)
    accent = (40, 60, 230) if error else (0, 210, 255)
    title_scale = max(0.9, min(1.6, width / 1000))
    put_text(frame, title, (50, 90), accent, title_scale, 3)

    y = 150
    for message in messages:
        wrapped = textwrap.wrap(message, width=max(42, width // 18)) or [""]
        for line in wrapped:
            put_text(frame, line, (50, y), (225, 225, 225), 0.75, 2)
            y += 38
        y += 10
    return frame


def load_yolo_model(
    model_path: Path,
    model_name: str,
    window_name: str,
    window_width: int,
    window_height: int,
) -> YOLO:
    loading = make_status_frame(
        "Memuat model YOLO",
        [model_name, str(model_path)],
        width=window_width,
        height=window_height,
    )
    cv2.imshow(window_name, loading)
    cv2.waitKey(1)
    return YOLO(str(model_path))


def create_window(name: str, width: int, height: int, fullscreen: bool) -> None:
    cv2.namedWindow(name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(name, width, height)
    if fullscreen:
        cv2.setWindowProperty(name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)


def save_screenshot(frame: np.ndarray, save_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    output_path = save_dir / f"cctv_{timestamp}.jpg"
    if not cv2.imwrite(str(output_path), frame):
        raise RuntimeError(f"Screenshot gagal disimpan: {output_path}")
    return output_path


def open_with_retry(
    config: dict[str, Any],
    source: str,
    window_name: str,
    window_width: int,
    window_height: int,
):
    retry_seconds = max(1.0, float(config.get("retry_seconds", 5)))

    while True:
        frame_source = create_frame_source(config, source_override=source)
        try:
            frame_source.open()
            return frame_source
        except Exception as exc:
            frame_source.release()
            message = str(exc).replace(source, redact_source(source))
            status_frame = make_status_frame(
                "Koneksi CCTV gagal",
                [
                    message,
                    f"Sumber: {redact_source(source)}",
                    "Periksa username/password dan path stream. Tekan R untuk mencoba sekarang atau Q untuk keluar.",
                ],
                width=window_width,
                height=window_height,
                error=True,
            )
            cv2.imshow(window_name, status_frame)

            deadline = time.monotonic() + retry_seconds
            while time.monotonic() < deadline:
                key = cv2.waitKey(100) & 0xFF
                if key in (ord("q"), 27):
                    return None
                if key == ord("r"):
                    break


def check_source(config: dict[str, Any], source: str) -> np.ndarray:
    frame_source = create_frame_source(config, source_override=source)
    try:
        frame_source.open()
        ok, frame = frame_source.read()
        if not ok or frame is None:
            raise RuntimeError("Kamera terbuka tetapi frame pertama belum diterima.")
        print(f"Koneksi frame OK: {frame.shape[1]}x{frame.shape[0]}")
        return frame
    finally:
        frame_source.release()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv(BACKEND_DIR / ".env", override=False)
    config = load_yaml_config(args.config)
    source = resolve_source(args, config)
    if source.lower().startswith("rtsp://"):
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    model_path = resolve_model(args, config)
    model_choices = build_model_choices(args, config, model_path)
    confidence = float(get_value(args, config, "conf", 0.50))
    imgsz = int(get_value(args, config, "imgsz", 960))
    device = str(get_value(args, config, "device", "auto"))
    abnormal_label = str(config.get("abnormal_label", "abnormal")).lower()

    print(f"Model: {model_path}")
    print(f"Sumber: {redact_source(source)}")
    if args.check_only:
        try:
            checked_model = YOLO(str(model_path))
            class_names = getattr(checked_model, "names", {})
            print(f"Model OK: {model_path.name}; classes={class_names}")
            checked_frame = check_source(config, source)
            check_kwargs: dict[str, Any] = {
                "source": checked_frame,
                "conf": confidence,
                "imgsz": imgsz,
                "verbose": False,
            }
            if device not in ("", "auto", "none"):
                check_kwargs["device"] = device
            checked_result = checked_model.predict(**check_kwargs)[0]
            print(
                "Inference OK: "
                f"device={getattr(checked_model, 'device', device)}; "
                f"detections={len(checked_result.boxes)}"
            )
            return 0
        except Exception as exc:
            message = str(exc).replace(source, redact_source(source))
            print(f"Koneksi gagal: {message}")
            return 2

    window_name = str(config.get("window_name", "Deteksi Mata Entok - CCTV"))
    window_width = int(config.get("window_width", 1600))
    window_height = int(config.get("window_height", 900))
    fullscreen = bool(config.get("fullscreen", False))
    save_dir = ensure_dir(resolve_config_path(config.get("save_dir", "../runs/detect/cctv_gui/screenshots"), config))
    auto_screenshot = bool(config.get("auto_screenshot", False))
    auto_screenshot_interval = max(
        0.1, float(config.get("auto_screenshot_interval_seconds", 4))
    )

    create_window(window_name, window_width, window_height, fullscreen)
    active_model_index = next(
        (
            index
            for index, (_, choice_path) in enumerate(model_choices)
            if choice_path == model_path.resolve()
        ),
        0,
    )
    model_name, model_path = model_choices[active_model_index]
    model = load_yolo_model(
        model_path, model_name, window_name, window_width, window_height
    )
    supports_abnormal = model_has_class(model, abnormal_label)
    frame_source = open_with_retry(
        config, source, window_name, window_width, window_height
    )
    if frame_source is None:
        cv2.destroyAllWindows()
        return 1
    ptz_controller, ptz_status = initialize_ptz(
        config, source, window_name, window_width, window_height
    )

    previous_time = time.perf_counter()
    smoothed_fps = 0.0
    paused = False
    reconnect_requested = False
    settings_requested = False
    active_device = device if device not in ("", "auto", "none") else "auto"
    last_display: np.ndarray | None = None
    last_detection_count = 0
    last_auto_screenshot_at = time.monotonic()

    try:
        while True:
            if not paused:
                ok, frame = frame_source.read()
                if not ok or frame is None:
                    if last_display is not None:
                        waiting = last_display.copy()
                    else:
                        waiting = make_status_frame(
                            "Menunggu frame CCTV",
                            ["Koneksi sedang dipulihkan secara otomatis..."],
                            width=window_width,
                            height=window_height,
                        )
                    put_text(waiting, "SINYAL KAMERA TERPUTUS", (35, 65), (0, 0, 255), 1.0, 3)
                    cv2.imshow(window_name, waiting)
                    key = cv2.waitKeyEx(30)
                    update_ptz_from_held_keys(ptz_controller, window_name)
                    if key in (ord("q"), ord("Q"), 27):
                        break
                    if key in (ord("r"), ord("R")):
                        frame_source.release()
                        reopened_source = open_with_retry(
                            config, source, window_name, window_width, window_height
                        )
                        if reopened_source is None:
                            break
                        frame_source = reopened_source
                        previous_time = time.perf_counter()
                    continue

                predict_kwargs: dict[str, Any] = {
                    "source": frame,
                    "conf": confidence,
                    "imgsz": imgsz,
                    "verbose": False,
                }
                if device not in ("", "auto", "none"):
                    predict_kwargs["device"] = device

                result = model.predict(**predict_kwargs)[0]
                active_device = str(getattr(model, "device", active_device))
                annotated = result.plot(line_width=2)
                now = time.perf_counter()
                instant_fps = 1.0 / max(now - previous_time, 1e-6)
                previous_time = now
                smoothed_fps = instant_fps if smoothed_fps == 0 else (0.85 * smoothed_fps + 0.15 * instant_fps)

                names = result.names
                labels = [names[int(box.cls[0])].lower() for box in result.boxes]
                abnormal_count = sum(label == abnormal_label for label in labels)
                last_detection_count = len(labels)
                last_display = draw_hud(
                    annotated,
                    fps=smoothed_fps,
                    detection_count=last_detection_count,
                    abnormal_count=abnormal_count,
                    confidence=confidence,
                    model_name=model_name,
                    device_name=active_device,
                    supports_abnormal=supports_abnormal,
                    paused=False,
                    auto_screenshot=auto_screenshot,
                    auto_screenshot_interval=auto_screenshot_interval,
                    ptz_status=ptz_status,
                    ptz_direction=(
                        ptz_controller.current_direction if ptz_controller else None
                    ),
                )

            if last_display is None:
                continue

            display_frame = last_display
            if paused:
                display_frame = last_display.copy()
                pause_text = "JEDA"
                pause_scale = max(0.42, min(0.62, display_frame.shape[1] / 3000))
                pause_size = cv2.getTextSize(
                    pause_text, cv2.FONT_HERSHEY_SIMPLEX, pause_scale, 1
                )[0]
                pause_x = display_frame.shape[1] - pause_size[0] - 14
                pause_y = display_frame.shape[0] - 8
                cv2.rectangle(
                    display_frame,
                    (pause_x - 8, pause_y - pause_size[1] - 7),
                    (display_frame.shape[1], display_frame.shape[0]),
                    (15, 15, 15),
                    -1,
                )
                cv2.putText(
                    display_frame,
                    pause_text,
                    (pause_x, pause_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    pause_scale,
                    (0, 165, 255),
                    1,
                    cv2.LINE_AA,
                )

            now = time.monotonic()
            if (
                auto_screenshot
                and not paused
                and now - last_auto_screenshot_at >= auto_screenshot_interval
            ):
                output_path = save_screenshot(display_frame, save_dir)
                last_auto_screenshot_at = now
                print(f"Screenshot otomatis disimpan: {output_path}")

            cv2.imshow(window_name, display_frame)
            key = cv2.waitKeyEx(1 if not paused else 30)
            held_keys_supported = update_ptz_from_held_keys(
                ptz_controller, window_name
            )
            try:
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
            if key in (ord("q"), ord("Q"), 27):
                break
            if key in (ord("p"), ord("P")):
                paused = not paused
            elif key in (ord("t"), ord("T")):
                auto_screenshot = not auto_screenshot
                last_auto_screenshot_at = time.monotonic()
                print(
                    "Screenshot otomatis "
                    + ("diaktifkan" if auto_screenshot else "dimatikan")
                )
            elif key in (ord("c"), ord("C")):
                output_path = save_screenshot(display_frame, save_dir)
                print(f"Screenshot disimpan: {output_path}")
            elif not held_keys_supported and key in (
                ord("w"),
                ord("W"),
                ord("s"),
                ord("S"),
                ord("a"),
                ord("A"),
                ord("d"),
                ord("D"),
            ):
                direction_by_key = {
                    ord("w"): "up",
                    ord("W"): "up",
                    ord("s"): "down",
                    ord("S"): "down",
                    ord("a"): "left",
                    ord("A"): "left",
                    ord("d"): "right",
                    ord("D"): "right",
                }
                if ptz_controller and ptz_controller.connected:
                    ptz_controller.start_move(
                        direction_by_key[key], auto_stop_after=0.4
                    )
            elif key in (ord("+"), ord("=")):
                confidence = min(0.95, round(confidence + 0.05, 2))
            elif key in (ord("-"), ord("_")):
                confidence = max(0.05, round(confidence - 0.05, 2))
            elif key in (ord("m"), ord("M"), ord("o"), ord("O")):
                candidate_index = -1
                if key in (ord("m"), ord("M")):
                    candidate_index = (
                        0
                        if active_model_index < 0
                        else (active_model_index + 1) % len(model_choices)
                    )
                    candidate_name, candidate_path = model_choices[candidate_index]
                else:
                    selected_path = choose_custom_model(model_path.parent)
                    if selected_path is None:
                        continue
                    if not selected_path.is_file():
                        print(f"Model tidak ditemukan: {selected_path}")
                        continue
                    if selected_path.suffix.lower() not in {".pt", ".onnx", ".engine"}:
                        print("Format model harus .pt, .onnx, atau .engine")
                        continue
                    candidate_path = selected_path
                    candidate_name = f"Custom: {selected_path.stem}"
                    for index, (choice_name, choice_path) in enumerate(model_choices):
                        if choice_path == selected_path:
                            candidate_index = index
                            candidate_name = choice_name
                            break

                try:
                    candidate_model = load_yolo_model(
                        candidate_path,
                        candidate_name,
                        window_name,
                        window_width,
                        window_height,
                    )
                except Exception as exc:
                    print(f"Model gagal dimuat, tetap memakai {model_name}: {exc}")
                    error_frame = make_status_frame(
                        "Model gagal dimuat",
                        [str(exc), f"Tetap memakai: {model_name}"],
                        width=window_width,
                        height=window_height,
                        error=True,
                    )
                    cv2.imshow(window_name, error_frame)
                    cv2.waitKey(1500)
                    continue

                model = candidate_model
                model_path = candidate_path
                model_name = candidate_name
                active_model_index = candidate_index
                supports_abnormal = model_has_class(model, abnormal_label)
                smoothed_fps = 0.0
                previous_time = time.perf_counter()
                print(f"Model aktif: {model_name} ({model_path})")
            elif key in (ord("r"), ord("R")):
                reconnect_requested = True
            elif key in (ord("g"), ord("G")):
                settings_requested = True
                break

            if reconnect_requested:
                frame_source.release()
                reopened_source = open_with_retry(
                    config, source, window_name, window_width, window_height
                )
                if reopened_source is None:
                    break
                frame_source = reopened_source
                reconnect_requested = False
                previous_time = time.perf_counter()
    finally:
        if ptz_controller is not None:
            ptz_controller.close()
        frame_source.release()
        cv2.destroyAllWindows()

    return SETTINGS_EXIT_CODE if settings_requested else 0


if __name__ == "__main__":
    raise SystemExit(main())
