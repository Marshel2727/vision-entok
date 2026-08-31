from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import cv2
import numpy as np
from PIL import ImageGrab


def normalize_source(source: Any):
    if isinstance(source, int):
        return source

    source_text = str(source)
    if source_text.isdigit():
        return int(source_text)

    return source_text


def redact_source(source: Any) -> str:
    """Sembunyikan credential URL sebelum ditampilkan ke log atau GUI."""
    source_text = str(source)

    try:
        parsed = urlsplit(source_text)
    except ValueError:
        return source_text

    if not parsed.scheme or parsed.hostname is None or parsed.username is None:
        return source_text

    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"

    return urlunsplit(
        (parsed.scheme, f"***:***@{host}", parsed.path, parsed.query, parsed.fragment)
    )


def parse_region(value: Any) -> tuple[int, int, int, int]:
    if isinstance(value, str):
        parts = [int(part.strip()) for part in value.split(",")]
    else:
        parts = [int(part) for part in value]

    if len(parts) != 4:
        raise ValueError("Region harus berisi left, top, width, height.")

    left, top, width, height = parts
    if width <= 0 or height <= 0:
        raise ValueError("Region width dan height harus lebih besar dari 0.")

    return left, top, width, height


class FrameSource:
    name = "base"

    def open(self) -> None:
        raise NotImplementedError

    def read(self) -> tuple[bool, np.ndarray | None]:
        raise NotImplementedError

    def release(self) -> None:
        raise NotImplementedError

    def request_reconnect(self) -> bool:
        return False

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "state": "connected",
            "connected": True,
            "frame_age_ms": None,
            "reconnect_attempt": 0,
            "next_retry_seconds": 0.0,
            "last_reconnect_at": None,
            "last_error": None,
        }


@dataclass
class OpenCVFrameSource(FrameSource):
    source: Any
    reconnect_delay: float = 1.0
    max_reconnect_attempts: int = 5
    stale_timeout: float = 3.0
    name: str = "opencv"
    _cap: cv2.VideoCapture | None = field(default=None, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _wake_event: threading.Event = field(default_factory=threading.Event, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _latest_frame: np.ndarray | None = field(default=None, init=False)
    _latest_frame_at: float = field(default=0.0, init=False)
    _last_read_frame_at: float = field(default=0.0, init=False)
    _state: str = field(default="disconnected", init=False)
    _last_error: str | None = field(default=None, init=False)
    _reconnect_attempt: int = field(default=0, init=False)
    _next_retry_at: float = field(default=0.0, init=False)
    _last_reconnect_at: float | None = field(default=None, init=False)

    def _create_capture(self) -> cv2.VideoCapture:
        source = normalize_source(self.source)
        if isinstance(source, str) and source.lower().startswith("rtsp://"):
            # Hindari fallback CAP_IMAGES yang dapat menulis URL bercredential
            # secara lengkap ke log ketika koneksi RTSP gagal.
            return cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        return cv2.VideoCapture(source)

    def open(self) -> None:
        self._stop_event.clear()
        self._wake_event.clear()
        capture = self._create_capture()
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(
                f"Source tidak bisa dibuka oleh OpenCV: {redact_source(self.source)}"
            )

        ok, frame = capture.read()
        if not ok or frame is None:
            capture.release()
            raise RuntimeError("Source terbuka tetapi frame pertama belum diterima.")

        now = time.monotonic()
        with self._lock:
            self._cap = capture
            self._latest_frame = frame
            self._latest_frame_at = now
            self._last_read_frame_at = now
            self._state = "connected"
            self._last_error = None
            self._reconnect_attempt = 0
            self._next_retry_at = 0.0

        self._thread = threading.Thread(
            target=self._reader_loop,
            name="entok-opencv-latest-frame",
            daemon=True,
        )
        self._thread.start()

    def read(self) -> tuple[bool, np.ndarray | None]:
        now = time.monotonic()
        with self._lock:
            frame = None if self._latest_frame is None else self._latest_frame.copy()
            frame_at = self._latest_frame_at
            if frame is not None:
                self._last_read_frame_at = frame_at

        if frame is None or not frame_at or now - frame_at > self.stale_timeout:
            return False, None
        return True, frame

    def release(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        self._close_capture()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._thread = None
        with self._lock:
            self._state = "stopped"

    def request_reconnect(self) -> bool:
        if self._stop_event.is_set():
            return False
        self._mark_disconnected("Reconnect diminta pengguna.")
        self._close_capture()
        self._wake_event.set()
        return True

    def status_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            age_ms = (
                max(0.0, (now - self._last_read_frame_at) * 1000)
                if self._last_read_frame_at
                else None
            )
            return {
                "state": self._state,
                "connected": self._state == "connected",
                "frame_age_ms": age_ms,
                "reconnect_attempt": self._reconnect_attempt,
                "next_retry_seconds": max(0.0, self._next_retry_at - now),
                "last_reconnect_at": self._last_reconnect_at,
                "last_error": self._last_error,
            }

    def _close_capture(self) -> None:
        with self._lock:
            capture = self._cap
            self._cap = None
        if capture is not None:
            capture.release()

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                capture = self._cap

            if capture is not None and capture.isOpened():
                ok, frame = capture.read()
                if ok and frame is not None:
                    now = time.monotonic()
                    with self._lock:
                        self._latest_frame = frame
                        self._latest_frame_at = now
                        self._state = "connected"
                        self._last_error = None
                    continue
                self._mark_disconnected("Pembacaan frame gagal.")
                self._close_capture()

            if self._stop_event.is_set():
                break
            self._reconnect_in_reader()

    def _mark_disconnected(self, message: str) -> None:
        with self._lock:
            self._state = "reconnecting"
            self._last_error = message
            self._latest_frame = None
            self._latest_frame_at = 0.0

    def _reconnect_in_reader(self) -> None:
        with self._lock:
            attempt = self._reconnect_attempt + 1
            self._reconnect_attempt = attempt
        capped_attempt = min(attempt, max(1, self.max_reconnect_attempts))
        delay = min(30.0, self.reconnect_delay * (2 ** (capped_attempt - 1)))
        with self._lock:
            self._state = "reconnecting"
            self._next_retry_at = time.monotonic() + delay

        self._wake_event.wait(delay)
        self._wake_event.clear()
        if self._stop_event.is_set():
            return

        capture = self._create_capture()
        if self._stop_event.is_set():
            capture.release()
            return
        if not capture.isOpened():
            capture.release()
            self._mark_disconnected(
                f"Reconnect gagal pada percobaan {attempt}."
            )
            return

        with self._lock:
            self._cap = capture
            self._state = "connected"
            self._last_error = None
            self._reconnect_attempt = 0
            self._next_retry_at = 0.0
            self._last_reconnect_at = time.time()
        print(f"[{self.name}] reconnect OK pada percobaan {attempt}")


@dataclass
class FFmpegFrameSource(FrameSource):
    source: str
    width: int
    height: int
    ffmpeg_path: str = "ffmpeg"
    rtsp_transport: str = "tcp"
    stale_timeout: float = 5.0
    reconnect_delay: float = 1.0
    input_args: list[str] = field(default_factory=list)
    output_args: list[str] = field(default_factory=list)
    name: str = "ffmpeg"
    _process: subprocess.Popen | None = field(default=None, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _latest_frame: np.ndarray | None = field(default=None, init=False)
    _last_frame_at: float = field(default=0.0, init=False)
    _last_read_frame_at: float = field(default=0.0, init=False)
    _last_reconnect_at: float | None = field(default=None, init=False)

    def open(self) -> None:
        self._stop_event.clear()
        self._start_process()

    def read(self) -> tuple[bool, np.ndarray | None]:
        now = time.time()

        with self._lock:
            frame = None if self._latest_frame is None else self._latest_frame.copy()
            last_frame_at = self._last_frame_at
            if frame is not None:
                self._last_read_frame_at = last_frame_at

        if frame is not None and now - last_frame_at <= self.stale_timeout:
            return True, frame

        if self._process is None or self._process.poll() is not None:
            self._restart_process()
        elif last_frame_at and now - last_frame_at > self.stale_timeout:
            print(f"[{self.name}] frame stale, restart ffmpeg")
            self._restart_process()

        return False, None

    def release(self) -> None:
        self._stop_event.set()
        self._stop_process()

    def status_snapshot(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            age_ms = (
                max(0.0, (now - self._last_read_frame_at) * 1000)
                if self._last_read_frame_at
                else None
            )
            alive = self._process is not None and self._process.poll() is None
            return {
                "state": "connected" if alive else "reconnecting",
                "connected": alive,
                "frame_age_ms": age_ms,
                "reconnect_attempt": 0,
                "next_retry_seconds": 0.0,
                "last_reconnect_at": self._last_reconnect_at,
                "last_error": None,
            }

    def _build_command(self) -> list[str]:
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
        ]

        if self.source.lower().startswith("rtsp://"):
            command += ["-rtsp_transport", self.rtsp_transport]

        command += self.input_args
        command += [
            "-i",
            self.source,
            "-an",
            "-vf",
            f"scale={self.width}:{self.height}",
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
        ]
        command += self.output_args
        command += ["pipe:1"]
        return command

    def _start_process(self) -> None:
        command = self._build_command()
        safe_command = [redact_source(part) for part in command]
        print(f"[{self.name}] start: {' '.join(safe_command)}")

        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=self.width * self.height * 3 * 4,
        )

        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def _restart_process(self) -> None:
        self._stop_process()
        time.sleep(self.reconnect_delay)
        with self._lock:
            self._latest_frame = None
            self._last_frame_at = 0.0
        self._start_process()
        self._last_reconnect_at = time.time()

    def _stop_process(self) -> None:
        process = self._process
        self._process = None

        if process is None:
            return

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

    def _reader_loop(self) -> None:
        frame_size = self.width * self.height * 3

        while not self._stop_event.is_set():
            process = self._process
            if process is None or process.stdout is None:
                break

            data = process.stdout.read(frame_size)
            if len(data) != frame_size:
                break

            frame = np.frombuffer(data, dtype=np.uint8).reshape(
                (self.height, self.width, 3)
            )

            with self._lock:
                self._latest_frame = frame
                self._last_frame_at = time.time()


@dataclass
class ScreenRegionFrameSource(FrameSource):
    region: tuple[int, int, int, int]
    fps_limit: float = 10.0
    name: str = "screen"
    _last_capture_at: float = field(default=0.0, init=False)

    def open(self) -> None:
        return None

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.fps_limit > 0:
            wait_time = (1 / self.fps_limit) - (time.time() - self._last_capture_at)
            if wait_time > 0:
                time.sleep(wait_time)

        left, top, width, height = self.region
        image = ImageGrab.grab(bbox=(left, top, left + width, top + height))
        frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        self._last_capture_at = time.time()
        return True, frame

    def release(self) -> None:
        return None


@dataclass
class ADBFrameSource(FrameSource):
    adb_path: str = "adb"
    serial: str | None = None
    crop: tuple[int, int, int, int] | None = None
    fps_limit: float = 5.0
    name: str = "adb"
    _last_capture_at: float = field(default=0.0, init=False)

    def open(self) -> None:
        command = [self.adb_path]
        if self.serial:
            command += ["-s", self.serial]
        command += ["get-state"]

        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0 or "device" not in result.stdout:
            raise RuntimeError(
                "ADB device tidak terbaca. Jalankan `adb devices` dan pastikan emulator/device aktif."
            )

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.fps_limit > 0:
            wait_time = (1 / self.fps_limit) - (time.time() - self._last_capture_at)
            if wait_time > 0:
                time.sleep(wait_time)

        command = [self.adb_path]
        if self.serial:
            command += ["-s", self.serial]
        command += ["exec-out", "screencap", "-p"]

        result = subprocess.run(command, capture_output=True)
        if result.returncode != 0:
            return False, None

        data = np.frombuffer(result.stdout, dtype=np.uint8)
        frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if frame is None:
            return False, None

        if self.crop is not None:
            left, top, width, height = self.crop
            frame = frame[top : top + height, left : left + width]

        self._last_capture_at = time.time()
        return True, frame

    def release(self) -> None:
        return None


def create_frame_source(
    config: dict[str, Any],
    source_override: str | None = None,
    source_type_override: str | None = None,
) -> FrameSource:
    source_type = (source_type_override or config.get("source_type") or "opencv").lower()
    source = source_override if source_override is not None else config.get("source", 0)

    if source_type in {"opencv", "cv2", "webcam", "rtsp"}:
        return OpenCVFrameSource(
            source=source,
            reconnect_delay=float(config.get("reconnect_delay", 1.0)),
            max_reconnect_attempts=int(config.get("max_reconnect_attempts", 5)),
            stale_timeout=float(config.get("stale_timeout", 3.0)),
        )

    if source_type in {"ffmpeg", "media_server", "mediamtx", "go2rtc"}:
        return FFmpegFrameSource(
            source=str(source),
            width=int(config.get("frame_width", 640)),
            height=int(config.get("frame_height", 360)),
            ffmpeg_path=str(config.get("ffmpeg_path", "ffmpeg")),
            rtsp_transport=str(config.get("rtsp_transport", "tcp")),
            stale_timeout=float(config.get("stale_timeout", 5.0)),
            reconnect_delay=float(config.get("reconnect_delay", 1.0)),
            input_args=list(config.get("ffmpeg_input_args", [])),
            output_args=list(config.get("ffmpeg_output_args", [])),
        )

    if source_type in {"screen", "window", "app_capture", "v380_app"}:
        return ScreenRegionFrameSource(
            region=parse_region(config.get("region", source)),
            fps_limit=float(config.get("fps_limit", 10.0)),
        )

    if source_type == "adb":
        crop = config.get("crop")
        return ADBFrameSource(
            adb_path=str(config.get("adb_path", "adb")),
            serial=config.get("serial"),
            crop=parse_region(crop) if crop else None,
            fps_limit=float(config.get("fps_limit", 5.0)),
        )

    raise ValueError(f"source_type tidak dikenal: {source_type}")


def ensure_dir(path_value: str | Path) -> Path:
    path = Path(path_value)
    path.mkdir(parents=True, exist_ok=True)
    return path
