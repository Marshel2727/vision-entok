import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

from entok_vision.vision.config_loader import load_yaml_config, resolve_config_path
from training.tools.dataset_preflight import validate_dataset_config


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_YAML = PROJECT_DIR / "data" / "training" / "datav1_v2_combined" / "data.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "experiments" / "active"
DEFAULT_MODEL_DIR = PROJECT_DIR / "src" / "entok_vision" / "models"
DEFAULT_CONFIG = PROJECT_DIR / "training" / "configs" / "train_datav1_v2_yolo26s.yaml"


def parse_args():
    parser = argparse.ArgumentParser(description="Train YOLO model untuk deteksi mata entok.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path config YAML training.",
    )
    parser.add_argument(
        "--data",
        default=None,
        help="Path ke data.yaml dataset YOLO.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model awal YOLO. Contoh: yolo26m.pt, yolo11m.pt, atau yolov8m.pt.",
    )
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--imgsz", type=int, default=None)
    parser.add_argument("--batch", type=int, default=None)
    parser.add_argument("--device", default=None, help="auto, cpu, 0, 0,1, dst.")
    parser.add_argument("--name", default=None)
    parser.add_argument("--patience", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--deploy-from",
        default=None,
        help="Salin weights dari folder run yang sudah diverifikasi ke folder model runtime.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validasi konfigurasi dan dataset lalu berhenti tanpa training.",
    )
    return parser.parse_args()


def get_value(args, config: dict, key: str, default):
    arg_value = getattr(args, key)
    if arg_value is not None:
        return arg_value
    return config.get(key, default)


def copy_best_weights(save_dir: Path) -> None:
    weights_dir = save_dir / "weights"
    best_weight = weights_dir / "best.pt"
    last_weight = weights_dir / "last.pt"

    if not best_weight.exists():
        print(f"best.pt tidak ditemukan di: {best_weight}")
        return

    DEFAULT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best_weight, DEFAULT_MODEL_DIR / "best.pt")

    if last_weight.exists():
        shutil.copy2(last_weight, DEFAULT_MODEL_DIR / "last.pt")

    print(f"Model terbaik disalin ke: {DEFAULT_MODEL_DIR / 'best.pt'}")


def main():
    args = parse_args()
    config = load_yaml_config(args.config)

    if args.deploy_from:
        copy_best_weights(Path(args.deploy_from).resolve())
        return

    data_value = get_value(args, config, "data", str(DEFAULT_DATA_YAML))
    data_yaml = resolve_config_path(data_value, config)
    model_value = get_value(args, config, "model", "yolo26s.pt")
    model_path = resolve_config_path(model_value, config)
    model_name = str(model_path) if model_path.is_file() else str(model_value)
    epochs = get_value(args, config, "epochs", 50)
    imgsz = get_value(args, config, "imgsz", 640)
    batch = get_value(args, config, "batch", 8)
    device = get_value(args, config, "device", "auto")
    name = get_value(args, config, "name", "entok_eye_yolo26m")
    patience = get_value(args, config, "patience", 20)
    workers = get_value(args, config, "workers", 0)

    if not data_yaml.exists():
        raise FileNotFoundError(
            f"data.yaml tidak ditemukan: {data_yaml}\n"
            "Pastikan dataset Roboflow YOLO sudah diextract dan path --data benar."
        )

    expected_names = config.get("expected_names")
    validate_dataset_config(data_yaml, expected_names=expected_names)
    if args.preflight_only:
        print("Preflight selesai. Training tidak dijalankan.")
        return

    model = YOLO(model_name)

    train_kwargs = {
        "data": str(data_yaml),
        "epochs": epochs,
        "imgsz": imgsz,
        "batch": batch,
        "project": str(DEFAULT_OUTPUT_DIR),
        "name": name,
        "patience": patience,
        "workers": workers,
        "exist_ok": False,
    }

    if device != "auto":
        train_kwargs["device"] = device

    results = model.train(**train_kwargs)
    print("Model hasil training tidak mengganti model aplikasi secara otomatis.")
    print(
        "Setelah hasilnya diverifikasi, deploy dengan: "
        f'python -m training.train --deploy-from "{results.save_dir}"'
    )


if __name__ == "__main__":
    main()
