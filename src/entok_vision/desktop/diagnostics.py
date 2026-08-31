from __future__ import annotations

import hashlib
import json
import platform
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import yaml

from . import APP_NAME, APP_VERSION
from .model_registry import resolved_model_choices
from .runtime_paths import RuntimePaths
from .settings import DesktopSettings
from .update_checker import check_for_updates


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_manifest(paths: RuntimePaths) -> dict[str, Any]:
    candidates = (
        paths.resource_root / "models" / "manifest.yaml",
        paths.resource_root / "src" / "entok_vision" / "models" / "manifest.yaml",
    )
    for candidate in candidates:
        if candidate.is_file():
            payload = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            return payload if isinstance(payload, dict) else {}
    return {}


def _runtime_snapshot(paths: RuntimePaths) -> dict[str, Any]:
    if not paths.diagnostics_file.is_file():
        return {"status": "Aplikasi kamera belum mengirim snapshot runtime."}
    try:
        payload = json.loads(paths.diagnostics_file.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"status": "Snapshot tidak valid."}
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": f"Snapshot tidak dapat dibaca: {exc}"}


def collect_diagnostics(
    paths: RuntimePaths,
    settings: DesktopSettings,
) -> dict[str, Any]:
    manifest = _model_manifest(paths)
    manifest_by_id = {
        str(item.get("id")): item
        for item in manifest.get("models", [])
        if isinstance(item, dict)
    }
    choices = resolved_model_choices(paths)
    definition, path = next(
        (choice for choice in choices if choice[0].id == settings.model_id),
        choices[0],
    )
    expected = manifest_by_id.get(definition.id, {})
    actual_sha256 = _sha256(path)
    expected_sha256 = str(expected.get("sha256", ""))
    models = [
        {
            "id": definition.id,
            "name": definition.name,
            "file": path.name,
            "sha256": actual_sha256,
            "checksum_ok": not expected_sha256 or actual_sha256 == expected_sha256,
            "active": True,
        }
    ]

    cuda_available = False
    gpu_name = "Tidak tersedia"
    torch_version = "Tidak tersedia"
    try:
        import torch

        torch_version = str(torch.__version__)
        cuda_available = bool(torch.cuda.is_available())
        if cuda_available:
            gpu_name = str(torch.cuda.get_device_name(0))
    except Exception as exc:
        gpu_name = f"Tidak dapat dibaca: {exc}"

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "application": {"name": APP_NAME, "version": APP_VERSION},
        "system": {
            "os": platform.platform(),
            "python": sys.version.split()[0],
            "torch": torch_version,
            "cuda_available": cuda_available,
            "gpu": gpu_name,
        },
        "configuration": {
            "portable": paths.portable,
            "source_type": settings.source_type,
            "performance_preset": settings.performance_preset,
            "device": settings.device,
            "imgsz": settings.imgsz,
            "target_fps": settings.target_fps,
            "config_dir": str(paths.config_dir),
            "log_file": str(paths.log_file),
        },
        "models": models,
        "runtime": _runtime_snapshot(paths),
    }


def show_diagnostics(
    paths: RuntimePaths,
    settings: DesktopSettings,
    *,
    parent: tk.Misc | None = None,
) -> None:
    owns_root = parent is None
    window: tk.Tk | tk.Toplevel
    if owns_root:
        window = tk.Tk()
    else:
        window = tk.Toplevel(parent)
    window.title(f"Diagnostik - {APP_NAME}")
    window.geometry("820x620")
    window.minsize(620, 440)

    text = tk.Text(window, wrap="none", font=("Consolas", 10))
    y_scroll = ttk.Scrollbar(window, orient="vertical", command=text.yview)
    x_scroll = ttk.Scrollbar(window, orient="horizontal", command=text.xview)
    text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
    text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=(10, 0))
    y_scroll.grid(row=0, column=1, sticky="ns", pady=(10, 0))
    x_scroll.grid(row=1, column=0, sticky="ew", padx=(10, 0))
    window.rowconfigure(0, weight=1)
    window.columnconfigure(0, weight=1)

    state: dict[str, Any] = {}

    def refresh() -> None:
        try:
            state.clear()
            state.update(collect_diagnostics(paths, settings))
            rendered = json.dumps(state, ensure_ascii=False, indent=2)
            text.configure(state="normal")
            text.delete("1.0", tk.END)
            text.insert("1.0", rendered)
            text.configure(state="disabled")
        except Exception as exc:
            messagebox.showerror("Diagnostik gagal", str(exc), parent=window)

    def export_report() -> None:
        destination = filedialog.asksaveasfilename(
            parent=window,
            title="Ekspor laporan diagnostik",
            initialfile=f"entok-vision-diagnostic-{datetime.now():%Y%m%d-%H%M%S}.json",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if destination:
            Path(destination).write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            messagebox.showinfo("Diagnostik", "Laporan berhasil diekspor.", parent=window)

    def check_updates() -> None:
        try:
            result = check_for_updates(APP_VERSION)
            if result["update_available"]:
                message = f"Versi {result['latest_version']} tersedia."
            else:
                message = f"Versi {APP_VERSION} sudah terbaru."
            messagebox.showinfo("Pemeriksaan pembaruan", message, parent=window)
        except Exception as exc:
            messagebox.showwarning(
                "Pemeriksaan pembaruan gagal", str(exc), parent=window
            )

    actions = ttk.Frame(window, padding=10)
    actions.grid(row=2, column=0, columnspan=2, sticky="e")
    ttk.Button(actions, text="Perbarui", command=refresh).pack(side=tk.LEFT, padx=4)
    ttk.Button(actions, text="Cek Update", command=check_updates).pack(side=tk.LEFT, padx=4)
    ttk.Button(actions, text="Ekspor JSON", command=export_report).pack(side=tk.LEFT, padx=4)
    ttk.Button(actions, text="Tutup", command=window.destroy).pack(side=tk.LEFT, padx=4)
    refresh()
    if owns_root:
        window.mainloop()
