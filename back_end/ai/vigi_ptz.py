from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit


DEFAULT_ONVIF_PORT = 2020
DEFAULT_FALLBACK_PORT = 80


@dataclass(frozen=True)
class PTZSettings:
    host: str
    ports: tuple[int, ...]
    username: str
    password: str
    speed: float = 0.35
    timeout_seconds: float = 5.0
    hold_timeout_seconds: float = 1.0


def _clamp(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        return max(minimum, min(float(value), maximum))
    except (TypeError, ValueError):
        return default


def _parse_ports(primary: Any, fallback: Any) -> tuple[int, ...]:
    values: list[Any] = [primary]
    if isinstance(fallback, (list, tuple)):
        values.extend(fallback)
    elif fallback not in (None, ""):
        values.extend(str(fallback).replace(";", ",").split(","))

    ports: list[int] = []
    for value in values:
        if value in (None, ""):
            continue
        try:
            port = int(str(value).strip())
        except ValueError as exc:
            raise ValueError(f"Port ONVIF bukan angka: {value}") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"Port ONVIF di luar rentang: {port}")
        if port not in ports:
            ports.append(port)
    if not ports:
        raise ValueError("Tidak ada port ONVIF yang dikonfigurasi")
    return tuple(ports)


def settings_from_source(
    source: str,
    config: Mapping[str, Any],
    environ: Mapping[str, str] | None = None,
) -> PTZSettings:
    environ = os.environ if environ is None else environ
    parsed = urlsplit(source)

    host = (
        environ.get("ONVIF_IP")
        or environ.get("CCTV_HOST")
        or parsed.hostname
        or ""
    ).strip()
    if not host:
        raise ValueError("Host ONVIF tidak ditemukan")

    rtsp_user = unquote(parsed.username) if parsed.username else ""
    rtsp_password = unquote(parsed.password) if parsed.password else ""
    username = (
        environ.get("ONVIF_USER")
        or rtsp_user
        or environ.get("CCTV_USERNAME")
        or "admin"
    ).strip()
    password = environ.get("ONVIF_PASS")
    if password is None:
        password = rtsp_password
    if not password:
        password = environ.get("CCTV_PASSWORD", "")

    primary_port = environ.get(
        "ONVIF_PORT", str(config.get("onvif_port", DEFAULT_ONVIF_PORT))
    )
    fallback_ports = environ.get(
        "ONVIF_FALLBACK_PORTS",
        config.get("onvif_fallback_ports", [DEFAULT_FALLBACK_PORT]),
    )
    return PTZSettings(
        host=host,
        ports=_parse_ports(primary_port, fallback_ports),
        username=username,
        password=password,
        speed=_clamp(config.get("ptz_speed", 0.35), 0.05, 1.0, 0.35),
        timeout_seconds=_clamp(
            config.get("onvif_timeout_seconds", 5.0), 0.5, 30.0, 5.0
        ),
        hold_timeout_seconds=_clamp(
            config.get("ptz_hold_timeout_seconds", 1.0), 0.3, 5.0, 1.0
        ),
    )


class VigiPTZ:
    DIRECTIONS = {
        "up": (0.0, 1.0),
        "down": (0.0, -1.0),
        "left": (-1.0, 0.0),
        "right": (1.0, 0.0),
    }

    def __init__(self, settings: PTZSettings):
        self.settings = settings
        self.last_error: str | None = None
        self.connected_port: int | None = None
        self.current_direction: str | None = None
        self._camera = None
        self._ptz = None
        self._profile_token = None
        self._lock = threading.RLock()
        self._stop_timer: threading.Timer | None = None
        self._motion_generation = 0
        self._last_hold_refresh = 0.0

    @property
    def connected(self) -> bool:
        return self._ptz is not None and self._profile_token is not None

    @property
    def endpoint(self) -> str:
        port = self.connected_port or self.settings.ports[0]
        return f"{self.settings.host}:{port}"

    def _safe_error(self, error: Exception | str) -> str:
        message = " ".join(str(error).split())
        if self.settings.password:
            message = message.replace(self.settings.password, "***")
        return message

    def connect(self) -> bool:
        try:
            from onvif import ONVIFCamera
            from zeep.transports import Transport
        except ImportError as exc:
            self.last_error = (
                "Library ONVIF belum terpasang. Jalankan pip install onvif-zeep."
            )
            print(f"PTZ tidak tersedia: {self.last_error}")
            return False

        errors: list[str] = []
        for port in self.settings.ports:
            try:
                print(f"Menghubungkan ONVIF PTZ ke {self.settings.host}:{port}...")
                transport = Transport(
                    timeout=self.settings.timeout_seconds,
                    operation_timeout=self.settings.timeout_seconds,
                )
                camera = ONVIFCamera(
                    self.settings.host,
                    port,
                    self.settings.username,
                    self.settings.password,
                    transport=transport,
                )
                media = camera.create_media_service()
                ptz = camera.create_ptz_service()
                profiles = media.GetProfiles()
                if not profiles:
                    raise RuntimeError("Kamera tidak mengembalikan media profile ONVIF")
                profile_token = getattr(profiles[0], "token", None)
                if not profile_token:
                    raise RuntimeError("Media profile ONVIF tidak memiliki token")

                self._camera = camera
                self._ptz = ptz
                self._profile_token = profile_token
                self.connected_port = port
                self.last_error = None
                print(f"ONVIF PTZ terhubung: {self.endpoint}")
                return True
            except Exception as exc:
                errors.append(f"{self.settings.host}:{port} ({self._safe_error(exc)})")

        self.last_error = "; ".join(errors) or "Koneksi ONVIF gagal"
        print(f"PTZ tidak tersedia: {self.last_error}")
        return False

    def _cancel_stop_timer_locked(self) -> None:
        if self._stop_timer is not None:
            self._stop_timer.cancel()
            self._stop_timer = None

    def _schedule_stop_locked(self, delay: float, generation: int) -> None:
        timer = threading.Timer(delay, self._stop_if_current, args=(generation,))
        timer.daemon = True
        self._stop_timer = timer
        timer.start()

    def _stop_if_current(self, generation: int) -> None:
        with self._lock:
            if generation == self._motion_generation:
                self.stop()

    def _continuous_move(self, pan: float, tilt: float) -> None:
        request = self._ptz.create_type("ContinuousMove")
        request.ProfileToken = self._profile_token
        status = self._ptz.GetStatus({"ProfileToken": self._profile_token})
        request.Velocity = status.Position
        pan_tilt = getattr(request.Velocity, "PanTilt", None)
        if pan_tilt is None:
            raise RuntimeError("Kamera tidak menyediakan kontrol PanTilt")
        pan_tilt.x = pan * self.settings.speed
        pan_tilt.y = tilt * self.settings.speed
        zoom = getattr(request.Velocity, "Zoom", None)
        if zoom is not None:
            zoom.x = 0
        self._ptz.ContinuousMove(request)

    def start_move(self, direction: str, auto_stop_after: float | None = None) -> bool:
        movement = self.DIRECTIONS.get(direction)
        if not self.connected or movement is None:
            return False

        hold_timeout = max(
            0.2,
            float(
                self.settings.hold_timeout_seconds
                if auto_stop_after is None
                else auto_stop_after
            ),
        )
        now = time.monotonic()
        with self._lock:
            if (
                self.current_direction == direction
                and now - self._last_hold_refresh < hold_timeout * 0.4
            ):
                return True

            self._cancel_stop_timer_locked()
            self._motion_generation += 1
            generation = self._motion_generation
            try:
                if self.current_direction != direction:
                    self._continuous_move(*movement)
                    self.current_direction = direction
                self._last_hold_refresh = now
                self._schedule_stop_locked(hold_timeout, generation)
                return True
            except Exception as exc:
                self.last_error = self._safe_error(exc)
                print(f"Perintah PTZ {direction} gagal: {self.last_error}")
                self.stop()
                return False

    def stop(self) -> bool:
        if not self.connected:
            return False
        with self._lock:
            self._cancel_stop_timer_locked()
            self._motion_generation += 1
            if self.current_direction is None:
                return True
            try:
                request = self._ptz.create_type("Stop")
                request.ProfileToken = self._profile_token
                request.PanTilt = True
                request.Zoom = False
                self._ptz.Stop(request)
                self.current_direction = None
                return True
            except Exception as exc:
                self.last_error = self._safe_error(exc)
                print(f"Perintah STOP PTZ gagal: {self.last_error}")
                return False

    def close(self) -> None:
        self.stop()
        with self._lock:
            self._cancel_stop_timer_locked()
            self._ptz = None
            self._camera = None
            self._profile_token = None
