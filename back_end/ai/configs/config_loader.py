from pathlib import Path
from typing import Any

import yaml


def load_yaml_config(config_path: str | Path | None) -> dict[str, Any]:
    if not config_path:
        return {}

    path = Path(config_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Config tidak ditemukan: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Format config harus object/dictionary: {path}")

    data["_config_dir"] = path.parent
    return data


def resolve_config_path(value: str | Path, config: dict[str, Any]) -> Path:
    path = Path(value)

    if path.is_absolute():
        return path

    config_dir = config.get("_config_dir")
    if config_dir:
        return (Path(config_dir) / path).resolve()

    return path.resolve()
