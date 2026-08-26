import argparse
import time
from datetime import datetime
from pathlib import Path

import cv2
from ultralytics import YOLO

from configs.config_loader import load_yaml_config, resolve_config_path
from frame_sources import create_frame_source, ensure_dir


AI_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = AI_DIR / "models" / "best.pt"
DEFAULT_CONFIG = AI_DIR / "configs" / "webcam_laptop.yaml"


def parse_args():
    parser = argparse.ArgumentParser(description="Test model YOLO dengan sumber frame modular.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path config YAML untuk test kamera.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Path model .pt hasil training.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Camera index, path video, URL RTSP, region capture, atau source lain sesuai source_type.",
    )
    parser.add_argument(
        "--source-type",
        default=None,
        help="opencv, ffmpeg, screen, adb. Default mengikuti config.",
    )
    parser.add_argument("--conf", type=float, default=None)
    parser.add_argument("--imgsz", type=int, default=None)
    parser.add_argument("--device", default=None, help="Device YOLO, contoh: cpu atau 0 untuk GPU.")
    return parser.parse_args()


def get_value(args, config: dict, key: str, default):
    arg_value = getattr(args, key)
    if arg_value is not None:
        return arg_value
    return config.get(key, default)


def normalize_source(source: str):
    if source.isdigit():
        return int(source)
    return source


def is_model_file_path(model_value: str) -> bool:
    return (
        "/" in model_value
        or "\\" in model_value
        or model_value.startswith(".")
        or Path(model_value).is_absolute()
    )


def main():
    args = parse_args()
    config = load_yaml_config(args.config)

    model_value = get_value(args, config, "model", str(DEFAULT_MODEL_PATH))
    source = None
    if args.source is not None:
        source = str(args.source)
    conf = get_value(args, config, "conf", 0.50)
    imgsz = get_value(args, config, "imgsz", 640)
    device = get_value(args, config, "device", "auto")
    window_name = config.get("window_name", "Deteksi Mata Entok")
    show_fps = bool(config.get("show_fps", True))
    show_window = bool(config.get("show_window", True))
    no_frame_sleep = float(config.get("no_frame_sleep", 0.2))
    save_abnormal = bool(config.get("save_abnormal", False))
    abnormal_label = str(config.get("abnormal_label", "abnormal")).lower()
    save_interval = float(config.get("save_interval_seconds", 5.0))
    save_dir = ensure_dir(config.get("save_dir", AI_DIR / "runs" / "detect" / "abnormal_frames"))
    last_save_at = 0.0

    model_source = model_value

    if is_model_file_path(model_value):
        model_path = resolve_config_path(model_value, config)

        if not model_path.exists():
            raise FileNotFoundError(
                f"Model tidak ditemukan: {model_path}\n"
                "Train dulu modelnya atau arahkan --model ke file .pt yang benar."
            )

        model_source = str(model_path)

    model = YOLO(model_source)
    frame_source = create_frame_source(
        config,
        source_override=source,
        source_type_override=args.source_type,
    )
    frame_source.open()

    previous_time = time.time()

    print(
        "Deteksi stream berjalan. Tekan Q untuk keluar jika show_window aktif. "
        "Tekan CTRL+C untuk mode headless."
    )

    try:
        while True:
            ok, frame = frame_source.read()

            if not ok or frame is None:
                print("Frame belum tersedia, menunggu reconnect/source...")
                time.sleep(no_frame_sleep)
                continue

            predict_kwargs = {
                "source": frame,
                "conf": conf,
                "imgsz": imgsz,
                "verbose": False,
            }
            # Biarkan Ultralytics memilih GPU bila tersedia, atau CPU bila tidak.
            # Nilai "auto" dipakai khusus oleh konfigurasi aplikasi ini dan tidak
            # diteruskan sebagai nilai device ke Ultralytics.
            if device not in (None, "", "auto"):
                predict_kwargs["device"] = device

            results = model.predict(**predict_kwargs)

            annotated_frame = results[0].plot()
            names = results[0].names
            detected_labels = [
                names[int(box.cls[0])].lower()
                for box in results[0].boxes
            ]
            has_abnormal = abnormal_label in detected_labels

            current_time = time.time()
            fps = 1 / max(current_time - previous_time, 1e-6)
            previous_time = current_time

            if show_fps:
                cv2.putText(
                    annotated_frame,
                    f"FPS: {fps:.1f}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

            if save_abnormal and has_abnormal and current_time - last_save_at >= save_interval:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = save_dir / f"abnormal_{timestamp}.jpg"
                cv2.imwrite(str(output_path), annotated_frame)
                last_save_at = current_time
                print(f"Frame abnormal disimpan: {output_path}")

            if show_window:
                cv2.imshow(window_name, annotated_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
    finally:
        frame_source.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
