# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


PACKAGING_DIR = Path(SPECPATH).resolve()
PROJECT_ROOT = PACKAGING_DIR.parents[1]
BACKEND_DIR = PROJECT_ROOT / "back_end"
ICON = PACKAGING_DIR / "assets" / "entok_vision_lite.ico"
MODEL_DIR = BACKEND_DIR / "desktop_lite" / "models"

datas = [
    (str(MODEL_DIR / "entok_normal_abnormal.pt"), "models"),
    (str(MODEL_DIR / "entok_normal_only.pt"), "models"),
    (str(MODEL_DIR / "entok_normal_only_datav2_960.pt"), "models"),
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
    [str(BACKEND_DIR / "desktop_lite" / "app.py")],
    pathex=[str(BACKEND_DIR)],
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
