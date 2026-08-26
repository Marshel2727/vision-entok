from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from ai import cctv_gui
from desktop_lite.model_registry import MODELS, resolved_model_choices
from desktop_lite.runtime_paths import RuntimePaths
from desktop_lite.security import protect_bytes, unprotect_bytes
from desktop_lite.settings import (
    DesktopSecrets,
    default_settings,
    load_settings,
    runtime_config_payload,
    save_settings,
    write_runtime_config,
)


@pytest.fixture()
def runtime_paths(tmp_path: Path) -> RuntimePaths:
    project_root = Path(__file__).resolve().parents[2]
    paths = RuntimePaths(
        executable_dir=project_root,
        resource_root=project_root,
        data_root=tmp_path,
        config_dir=tmp_path / "config",
        security_dir=tmp_path / "security",
        log_dir=tmp_path / "logs",
        temp_dir=tmp_path / "temp",
        custom_model_dir=tmp_path / "models" / "custom",
        portable=False,
    )
    paths.ensure_directories()
    return paths


@pytest.mark.skipif(os.name != "nt", reason="DPAPI hanya tersedia di Windows")
def test_dpapi_round_trip() -> None:
    plaintext = b"rtsp://admin:secret@example/live"
    encrypted = protect_bytes(plaintext)
    assert encrypted != plaintext
    assert unprotect_bytes(encrypted) == plaintext


def test_settings_keep_credentials_out_of_plaintext(runtime_paths: RuntimePaths) -> None:
    settings = default_settings()
    secrets = DesktopSecrets(
        rtsp_url="rtsp://admin:secret@example/live",
        onvif_username="admin",
        onvif_password="secret",
    )
    save_settings(runtime_paths, settings, secrets)

    loaded = load_settings(runtime_paths)
    assert loaded is not None
    assert loaded[1] == secrets
    assert "secret" not in runtime_paths.settings_file.read_text(encoding="utf-8")

    runtime_config = write_runtime_config(loaded[0], runtime_paths)
    assert "secret" not in runtime_config.read_text(encoding="utf-8")


def test_runtime_config_uses_three_stable_model_paths(runtime_paths: RuntimePaths) -> None:
    settings = default_settings()
    payload = runtime_config_payload(settings, runtime_paths)

    assert len(payload["models"]) == 3
    assert Path(payload["model"]).is_file()
    assert all(Path(item["path"]).is_file() for item in payload["models"])
    assert payload["save_dir"] == settings.screenshot_dir
    assert payload["auto_screenshot_interval_seconds"] == 4.0


def test_model_registry_resolves_all_bundled_models(runtime_paths: RuntimePaths) -> None:
    choices = resolved_model_choices(runtime_paths)
    assert [definition.id for definition, _ in choices] == [model.id for model in MODELS]
    assert all(path.is_file() for _, path in choices)


def test_webcam_runtime_config_has_no_rtsp_source(runtime_paths: RuntimePaths) -> None:
    settings = default_settings()
    settings.source_type = "webcam"
    settings.webcam_index = 2
    payload = runtime_config_payload(settings, runtime_paths)

    assert payload["source"] == 2
    assert payload["ptz_enabled"] is False


def test_runtime_yaml_is_valid(runtime_paths: RuntimePaths) -> None:
    config_path = write_runtime_config(default_settings(), runtime_paths)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["window_name"] == "Entok Vision Lite"
    assert payload["models"][0]["name"] == "Normal + Abnormal"


def test_cctv_gui_accepts_in_process_argv() -> None:
    args = cctv_gui.parse_args(["--config", "example.yaml", "--check-only"])
    assert args.config == "example.yaml"
    assert args.check_only is True
