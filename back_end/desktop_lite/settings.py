from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from .model_registry import DEFAULT_MODEL_ID, MODELS, model_by_id, resolve_model_path
from .runtime_paths import RuntimePaths
from .security import load_encrypted_json, save_encrypted_json


SETTINGS_VERSION = 1


@dataclass
class DesktopSettings:
    version: int = SETTINGS_VERSION
    source_type: str = "rtsp"
    webcam_index: int = 0
    model_id: str = DEFAULT_MODEL_ID
    confidence: float = 0.25
    imgsz: int = 960
    device: str = "auto"
    ptz_enabled: bool = True
    onvif_port: int = 2020
    onvif_fallback_ports: list[int] | None = None
    screenshot_dir: str = ""
    auto_screenshot: bool = True
    auto_screenshot_interval_seconds: float = 4.0
    window_width: int = 1600
    window_height: int = 900
    fullscreen: bool = False

    def __post_init__(self) -> None:
        if self.onvif_fallback_ports is None:
            self.onvif_fallback_ports = [80]

    def validate(self) -> None:
        if self.version != SETTINGS_VERSION:
            raise ValueError(f"Versi konfigurasi tidak didukung: {self.version}")
        if self.source_type not in {"rtsp", "webcam"}:
            raise ValueError("Sumber kamera harus RTSP atau webcam.")
        if self.webcam_index < 0:
            raise ValueError("Indeks webcam tidak boleh negatif.")
        model_by_id(self.model_id)
        if not 0.05 <= self.confidence <= 0.95:
            raise ValueError("Confidence harus berada pada rentang 0.05 sampai 0.95.")
        if not 320 <= self.imgsz <= 2048:
            raise ValueError("Ukuran inferensi harus berada pada rentang 320 sampai 2048.")
        if self.device not in {"auto", "cpu", "0"}:
            raise ValueError("Device harus auto, cpu, atau 0.")
        if not 1 <= self.onvif_port <= 65535:
            raise ValueError("Port ONVIF tidak valid.")
        for port in self.onvif_fallback_ports or []:
            if not 1 <= int(port) <= 65535:
                raise ValueError("Fallback port ONVIF tidak valid.")
        if self.auto_screenshot_interval_seconds < 0.1:
            raise ValueError("Interval screenshot minimal 0.1 detik.")
        if not self.screenshot_dir.strip():
            raise ValueError("Folder screenshot belum dipilih.")


@dataclass
class DesktopSecrets:
    rtsp_url: str = ""
    onvif_username: str = ""
    onvif_password: str = ""

    def validate_for(self, settings: DesktopSettings) -> None:
        if settings.source_type == "rtsp" and not self.rtsp_url.strip():
            raise ValueError("URL RTSP belum diisi.")


def default_settings() -> DesktopSettings:
    return DesktopSettings(
        screenshot_dir=str(Path.home() / "Pictures" / "Entok Vision Lite")
    )


def load_settings(paths: RuntimePaths) -> tuple[DesktopSettings, DesktopSecrets] | None:
    if not paths.settings_file.is_file():
        return None
    payload = json.loads(paths.settings_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Format settings.json tidak valid.")
    settings = DesktopSettings(**payload)
    secrets = DesktopSecrets(**load_encrypted_json(paths.secrets_file))
    settings.validate()
    secrets.validate_for(settings)
    return settings, secrets


def save_settings(
    paths: RuntimePaths,
    settings: DesktopSettings,
    secrets: DesktopSecrets,
) -> None:
    settings.validate()
    secrets.validate_for(settings)
    paths.ensure_directories()
    temp_path = paths.settings_file.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, paths.settings_file)
    save_encrypted_json(paths.secrets_file, asdict(secrets))


def apply_secret_environment(settings: DesktopSettings, secrets: DesktopSecrets) -> None:
    if settings.source_type == "rtsp":
        os.environ["CCTV_RTSP_URL"] = secrets.rtsp_url.strip()
    else:
        os.environ.pop("CCTV_RTSP_URL", None)

    secret_env = {
        "ONVIF_USER": secrets.onvif_username.strip(),
        "ONVIF_PASS": secrets.onvif_password,
        "ONVIF_PORT": str(settings.onvif_port),
    }
    for key, value in secret_env.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


def runtime_config_payload(settings: DesktopSettings, paths: RuntimePaths) -> dict[str, Any]:
    choices = []
    for model in MODELS:
        choices.append(
            {"name": model.name, "path": str(resolve_model_path(model, paths))}
        )
    active_model = resolve_model_path(model_by_id(settings.model_id), paths)
    payload: dict[str, Any] = {
        "source_env": "CCTV_RTSP_URL",
        "source_type": "opencv",
        "model": str(active_model),
        "models": choices,
        "conf": settings.confidence,
        "imgsz": settings.imgsz,
        "device": settings.device,
        "abnormal_label": "abnormal",
        "window_name": "Entok Vision Lite",
        "window_width": settings.window_width,
        "window_height": settings.window_height,
        "fullscreen": settings.fullscreen,
        "retry_seconds": 5,
        "reconnect_delay": 1,
        "max_reconnect_attempts": 3,
        "ptz_enabled": settings.ptz_enabled and settings.source_type == "rtsp",
        "onvif_port": settings.onvif_port,
        "onvif_fallback_ports": settings.onvif_fallback_ports or [80],
        "onvif_timeout_seconds": 5,
        "ptz_speed": 0.35,
        "ptz_hold_timeout_seconds": 1.0,
        "save_dir": settings.screenshot_dir,
        "auto_screenshot": settings.auto_screenshot,
        "auto_screenshot_interval_seconds": settings.auto_screenshot_interval_seconds,
    }
    if settings.source_type == "webcam":
        payload["source"] = settings.webcam_index
    return payload


def write_runtime_config(settings: DesktopSettings, paths: RuntimePaths) -> Path:
    payload = runtime_config_payload(settings, paths)
    paths.runtime_config_file.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return paths.runtime_config_file


def reset_persisted_settings(paths: RuntimePaths) -> None:
    for path in (paths.settings_file, paths.secrets_file, paths.runtime_config_file):
        if path.is_file():
            path.unlink()
