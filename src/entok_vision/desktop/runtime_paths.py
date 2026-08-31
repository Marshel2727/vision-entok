from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


APP_DATA_DIRNAME = "EntokVisionLite"


@dataclass(frozen=True)
class RuntimePaths:
    executable_dir: Path
    resource_root: Path
    data_root: Path
    config_dir: Path
    security_dir: Path
    log_dir: Path
    temp_dir: Path
    custom_model_dir: Path
    portable: bool

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def secrets_file(self) -> Path:
        return self.security_dir / "secrets.dat"

    @property
    def runtime_config_file(self) -> Path:
        return self.temp_dir / "cctv_gui.runtime.yaml"

    @property
    def log_file(self) -> Path:
        return self.log_dir / "application.log"

    @property
    def diagnostics_file(self) -> Path:
        return self.temp_dir / "diagnostics-runtime.json"

    def ensure_directories(self) -> None:
        for path in (
            self.data_root,
            self.config_dir,
            self.security_dir,
            self.log_dir,
            self.temp_dir,
            self.custom_model_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def executable_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def resource_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root).resolve()
    return Path(__file__).resolve().parents[3]


def resolve_runtime_paths(force_portable: bool = False) -> RuntimePaths:
    exe_dir = executable_dir()
    portable = force_portable or (exe_dir / "portable.flag").is_file()
    if portable:
        data_root = exe_dir / "data"
    else:
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            data_root = Path(local_app_data) / APP_DATA_DIRNAME
        else:
            data_root = Path.home() / "AppData" / "Local" / APP_DATA_DIRNAME

    paths = RuntimePaths(
        executable_dir=exe_dir,
        resource_root=resource_root(),
        data_root=data_root,
        config_dir=data_root / "config",
        security_dir=data_root / "security",
        log_dir=data_root / "logs",
        temp_dir=data_root / "temp",
        custom_model_dir=data_root / "models" / "custom",
        portable=portable,
    )
    paths.ensure_directories()
    return paths
