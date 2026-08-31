from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_UPDATE_MANIFEST_URL = (
    "https://github.com/Marshel2727/vision-entok/releases/latest/download/"
    "websetup-manifest.json"
)


def _version_tuple(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lower().lstrip("v")
    parts: list[int] = []
    for part in cleaned.split("."):
        digits = "".join(character for character in part if character.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def check_for_updates(current_version: str, timeout: float = 5.0) -> dict[str, Any]:
    url = os.getenv("ENTOK_UPDATE_MANIFEST_URL", DEFAULT_UPDATE_MANIFEST_URL).strip()
    request = Request(url, headers={"User-Agent": "EntokVisionLite-update-check"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    latest_version = str(payload.get("version", "")).strip()
    if not latest_version:
        raise ValueError("Manifest pembaruan tidak memiliki field version.")
    return {
        "current_version": current_version,
        "latest_version": latest_version,
        "update_available": _version_tuple(latest_version) > _version_tuple(current_version),
        "release_url": str(payload.get("release_url", "")),
        "manifest_url": url,
    }
