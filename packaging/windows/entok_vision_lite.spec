# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


PACKAGING_DIR = Path(SPECPATH).resolve()
PROJECT_ROOT = PACKAGING_DIR.parents[1]
SOURCE_DIR = PROJECT_ROOT / "src"
ICON = PACKAGING_DIR / "assets" / "entok_vision_lite.ico"
MODEL_DIR = SOURCE_DIR / "entok_vision" / "models"
MODEL_FILES = {
    "yolo26s-combined": "entok_yolo26s_combined.pt",
    "normal-abnormal": "entok_normal_abnormal.pt",
    "normal-only": "entok_normal_only.pt",
    "normal-only-datav2-960": "entok_normal_only_datav2_960.pt",
}

model_set = os.environ.get("ENTOK_MODEL_SET", "production").strip().lower()
if model_set not in {"production", "all"}:
    raise ValueError("ENTOK_MODEL_SET harus production atau all")
default_model_id = (MODEL_DIR / "default_model.txt").read_text(encoding="utf-8").strip()
if default_model_id not in MODEL_FILES:
    raise ValueError(f"Model default tidak dikenal: {default_model_id}")
selected_model_files = (
    list(MODEL_FILES.values())
    if model_set == "all"
    else [MODEL_FILES[default_model_id]]
)

datas = [
    (str(MODEL_DIR / filename), "models")
    for filename in selected_model_files
    if (MODEL_DIR / filename).is_file()
]
if len(datas) != len(selected_model_files):
    missing = [name for name in selected_model_files if not (MODEL_DIR / name).is_file()]
    raise FileNotFoundError(f"Model untuk paket {model_set} tidak ditemukan: {missing}")
datas += [
    (str(MODEL_DIR / "manifest.yaml"), "models"),
    (str(MODEL_DIR / "default_model.txt"), "models"),
]
binaries = []
hiddenimports = [
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.ttk",
]

datas += collect_data_files("onvif")
hiddenimports += collect_submodules("onvif")
hiddenimports += collect_submodules("zeep")
for package in ("ultralytics", "torch", "torchvision", "opencv-python"):
    try:
        datas += copy_metadata(package)
    except Exception:
        pass

a = Analysis(
    [str(SOURCE_DIR / "entok_vision" / "desktop" / "app.py")],
    pathex=[str(SOURCE_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "pymysql",
        "alembic",
        "pytest",
        "ultralytics.trackers",
        "ultralytics.solutions",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EntokVisionLite",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EntokVisionLite",
)
