from __future__ import annotations

import argparse
import os
import subprocess
import traceback
from pathlib import Path
from tkinter import messagebox

from desktop_lite import APP_NAME, APP_VERSION
from desktop_lite.logging_utils import configure_logging
from desktop_lite.runtime_paths import RuntimePaths, resolve_runtime_paths
from desktop_lite.settings import (
    DesktopSecrets,
    DesktopSettings,
    apply_secret_environment,
    default_settings,
    load_settings,
    reset_persisted_settings,
    save_settings,
    write_runtime_config,
)
from desktop_lite.single_instance import SingleInstance


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--settings", action="store_true", help="Buka pengaturan lalu keluar.")
    parser.add_argument("--check-only", action="store_true", help="Validasi model dan kamera.")
    parser.add_argument("--reset-settings", action="store_true", help="Hapus konfigurasi setelah konfirmasi.")
    parser.add_argument("--portable", action="store_true", help="Gunakan folder data portable.")
    parser.add_argument("--version", action="store_true", help="Catat versi aplikasi lalu keluar.")
    return parser.parse_args(argv)


def open_folder(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


def show_fatal_error(paths: RuntimePaths, error: BaseException) -> None:
    answer = messagebox.askyesno(
        f"{APP_NAME} - Kesalahan",
        f"Aplikasi tidak dapat dijalankan.\n\n{error}\n\nBuka folder log?",
    )
    if answer:
        open_folder(paths.log_dir)


def edit_settings(
    paths: RuntimePaths,
    current: tuple[DesktopSettings, DesktopSecrets] | None,
) -> tuple[DesktopSettings, DesktopSecrets] | None:
    from desktop_lite.settings_dialog import show_settings_dialog

    settings, secrets = current or (default_settings(), DesktopSecrets())
    edited = show_settings_dialog(paths, settings, secrets)
    if edited is None:
        return None
    save_settings(paths, *edited)
    return edited


def run_application(args: argparse.Namespace, paths: RuntimePaths) -> int:
    current = load_settings(paths)
    if args.reset_settings:
        if messagebox.askyesno(
            "Reset Pengaturan",
            "Hapus konfigurasi dan credential Entok Vision Lite? Screenshot tidak dihapus.",
        ):
            reset_persisted_settings(paths)
            messagebox.showinfo("Reset Pengaturan", "Pengaturan berhasil dihapus.")
        return 0

    if current is None or args.settings:
        current = edit_settings(paths, current)
        if current is None:
            return 0
        if args.settings:
            return 0

    # Impor OpenCV, PyTorch, dan Ultralytics cukup mahal. Tunda sampai wizard
    # selesai agar layar konfigurasi pertama muncul tanpa menunggu runtime AI.
    from ai import cctv_gui

    while current is not None:
        settings, secrets = current
        apply_secret_environment(settings, secrets)
        config_path = write_runtime_config(settings, paths)
        gui_args = ["--config", str(config_path)]
        if args.check_only:
            gui_args.append("--check-only")
        exit_code = cctv_gui.main(gui_args)
        if exit_code != cctv_gui.SETTINGS_EXIT_CODE:
            return exit_code
        updated = edit_settings(paths, current)
        if updated is not None:
            current = updated
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = resolve_runtime_paths(force_portable=args.portable)
    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    os.environ.setdefault("YOLO_CONFIG_DIR", str(paths.config_dir / "ultralytics"))
    logger = configure_logging(paths.log_file)
    logger.info("%s %s starting; portable=%s", APP_NAME, APP_VERSION, paths.portable)
    if args.version:
        logger.info("Version check: %s %s", APP_NAME, APP_VERSION)
        return 0

    with SingleInstance() as instance:
        if not instance.acquire():
            messagebox.showinfo(APP_NAME, "Entok Vision Lite sudah berjalan.")
            return 0
        try:
            return run_application(args, paths)
        except Exception as exc:
            logger.error("Fatal error:\n%s", traceback.format_exc())
            show_fatal_error(paths, exc)
            return 1
        finally:
            logger.info("%s stopped", APP_NAME)


if __name__ == "__main__":
    raise SystemExit(main())
