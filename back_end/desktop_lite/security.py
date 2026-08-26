from __future__ import annotations

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import Any


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _require_windows() -> None:
    if os.name != "nt":
        raise RuntimeError("Penyimpanan credential Entok Vision Lite memerlukan Windows DPAPI.")


def _blob_from_bytes(value: bytes) -> tuple[DataBlob, ctypes.Array[Any]]:
    buffer = ctypes.create_string_buffer(value)
    blob = DataBlob(
        len(value),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    return blob, buffer


def protect_bytes(value: bytes) -> bytes:
    _require_windows()
    in_blob, keepalive = _blob_from_bytes(value)
    out_blob = DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "Entok Vision Lite",
        None,
        None,
        None,
        0x01,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        del keepalive
        kernel32.LocalFree(ctypes.cast(out_blob.pbData, wintypes.HLOCAL))


def unprotect_bytes(value: bytes) -> bytes:
    _require_windows()
    in_blob, keepalive = _blob_from_bytes(value)
    out_blob = DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0x01,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        del keepalive
        kernel32.LocalFree(ctypes.cast(out_blob.pbData, wintypes.HLOCAL))


def save_encrypted_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = protect_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_bytes(encrypted)
    os.replace(temp_path, path)


def load_encrypted_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    decrypted = unprotect_bytes(path.read_bytes())
    payload = json.loads(decrypted.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Format credential tersimpan tidak valid.")
    return payload
