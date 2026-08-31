from __future__ import annotations

import os
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from entok_vision.vision.frame_sources import create_frame_source, redact_source
from entok_vision.vision.vigi_ptz import VigiPTZ, settings_from_source

from .model_registry import model_by_id, resolve_model_path, resolved_model_choices
from .runtime_paths import RuntimePaths
from .settings import PERFORMANCE_PRESETS, DesktopSecrets, DesktopSettings


class SettingsDialog:
    def __init__(
        self,
        paths: RuntimePaths,
        settings: DesktopSettings,
        secrets: DesktopSecrets,
    ) -> None:
        self.paths = paths
        self.initial_settings = settings
        self.initial_secrets = secrets
        self.result: tuple[DesktopSettings, DesktopSecrets] | None = None
        self.available_models = [
            definition for definition, _ in resolved_model_choices(paths)
        ]
        selected_model = next(
            (model for model in self.available_models if model.id == settings.model_id),
            self.available_models[0],
        )

        self.root = tk.Tk()
        self.root.title("Pengaturan Entok Vision Lite")
        self.root.geometry("760x680")
        self.root.minsize(620, 520)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

        self.source_type = tk.StringVar(value=settings.source_type)
        self.rtsp_url = tk.StringVar(value=secrets.rtsp_url)
        self.webcam_index = tk.IntVar(value=settings.webcam_index)
        self.model_name = tk.StringVar(value=selected_model.name)
        self.performance_preset = tk.StringVar(
            value=str(PERFORMANCE_PRESETS[settings.performance_preset]["label"])
        )
        self.device = tk.StringVar(value=settings.device)
        self.confidence = tk.DoubleVar(value=settings.confidence)
        self.imgsz = tk.IntVar(value=settings.imgsz)
        self.ptz_enabled = tk.BooleanVar(value=settings.ptz_enabled)
        self.onvif_user = tk.StringVar(value=secrets.onvif_username)
        self.onvif_password = tk.StringVar(value=secrets.onvif_password)
        self.onvif_port = tk.IntVar(value=settings.onvif_port)
        self.screenshot_dir = tk.StringVar(value=settings.screenshot_dir)
        self.auto_screenshot = tk.BooleanVar(value=settings.auto_screenshot)
        self.screenshot_interval = tk.DoubleVar(
            value=settings.auto_screenshot_interval_seconds
        )
        self.show_credentials = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Isi pengaturan lalu lakukan pengujian kamera.")

        self._build()
        self._update_source_controls()

    def _build(self) -> None:
        shell = ttk.Frame(self.root)
        shell.pack(fill=tk.BOTH, expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        canvas = tk.Canvas(shell, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(shell, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        outer = ttk.Frame(canvas, padding=14)
        content_window = canvas.create_window((0, 0), window=outer, anchor="nw")
        outer.columnconfigure(0, weight=1)

        def update_scroll_region(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_content_width(event: tk.Event) -> None:
            canvas.itemconfigure(content_window, width=event.width)

        def scroll_content(event: tk.Event) -> None:
            if canvas.winfo_height() < outer.winfo_reqheight():
                canvas.yview_scroll(int(-event.delta / 120), "units")

        outer.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", fit_content_width)
        self.root.bind_all("<MouseWheel>", scroll_content)

        source_box = ttk.LabelFrame(outer, text="1. Sumber video", padding=10)
        source_box.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        source_box.columnconfigure(1, weight=1)
        ttk.Radiobutton(
            source_box,
            text="CCTV RTSP",
            value="rtsp",
            variable=self.source_type,
            command=self._update_source_controls,
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            source_box,
            text="Webcam",
            value="webcam",
            variable=self.source_type,
            command=self._update_source_controls,
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(source_box, text="URL RTSP").grid(row=1, column=0, sticky="w", pady=5)
        self.rtsp_entry = ttk.Entry(source_box, textvariable=self.rtsp_url, show="•")
        self.rtsp_entry.grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(source_box, text="Indeks webcam").grid(row=2, column=0, sticky="w", pady=5)
        self.webcam_spin = ttk.Spinbox(
            source_box, from_=0, to=10, textvariable=self.webcam_index, width=8
        )
        self.webcam_spin.grid(row=2, column=1, sticky="w", pady=5)
        ttk.Checkbutton(
            source_box,
            text="Tampilkan URL/kredensial",
            variable=self.show_credentials,
            command=self._toggle_credentials,
        ).grid(row=3, column=1, sticky="w")
        ttk.Button(source_box, text="Uji Kamera", command=self._test_camera).grid(
            row=4, column=1, sticky="e", pady=(8, 0)
        )

        model_box = ttk.LabelFrame(outer, text="2. Model dan perangkat", padding=10)
        model_box.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        model_box.columnconfigure(1, weight=1)
        ttk.Label(model_box, text="Model awal").grid(row=0, column=0, sticky="w", pady=5)
        model_combo = ttk.Combobox(
            model_box,
            state="readonly",
            values=[model.name for model in self.available_models],
            textvariable=self.model_name,
        )
        model_combo.grid(row=0, column=1, sticky="ew", pady=5)
        for index, model in enumerate(self.available_models):
            if model.id == self.initial_settings.model_id:
                model_combo.current(index)
                break
        ttk.Label(model_box, text="Preset performa").grid(
            row=1, column=0, sticky="w", pady=5
        )
        preset_combo = ttk.Combobox(
            model_box,
            state="readonly",
            values=[str(value["label"]) for value in PERFORMANCE_PRESETS.values()],
            textvariable=self.performance_preset,
        )
        preset_combo.grid(row=1, column=1, sticky="ew", pady=5)
        preset_combo.bind("<<ComboboxSelected>>", self._apply_performance_preset)
        ttk.Label(model_box, text="Device").grid(row=2, column=0, sticky="w", pady=5)
        self.device_combo = ttk.Combobox(
            model_box,
            state="disabled",
            values=["auto", "cpu", "0"],
            textvariable=self.device,
            width=12,
        )
        self.device_combo.grid(row=2, column=1, sticky="w", pady=5)
        ttk.Label(model_box, text="Confidence").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Spinbox(
            model_box,
            from_=0.05,
            to=0.95,
            increment=0.05,
            textvariable=self.confidence,
            width=12,
        ).grid(row=3, column=1, sticky="w", pady=5)
        ttk.Label(model_box, text="Ukuran inferensi").grid(row=4, column=0, sticky="w", pady=5)
        self.imgsz_combo = ttk.Combobox(
            model_box,
            state="disabled",
            values=[640, 768, 960],
            textvariable=self.imgsz,
            width=12,
        )
        self.imgsz_combo.grid(row=4, column=1, sticky="w", pady=5)
        ttk.Button(model_box, text="Uji Model", command=self._test_model).grid(
            row=5, column=1, sticky="e", pady=(8, 0)
        )

        ptz_box = ttk.LabelFrame(outer, text="3. PTZ ONVIF (opsional)", padding=10)
        ptz_box.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ptz_box.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            ptz_box, text="Aktifkan PTZ", variable=self.ptz_enabled
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(ptz_box, text="Username").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(ptz_box, textvariable=self.onvif_user).grid(
            row=1, column=1, sticky="ew", pady=5
        )
        ttk.Label(ptz_box, text="Password").grid(row=2, column=0, sticky="w", pady=5)
        self.onvif_pass_entry = ttk.Entry(
            ptz_box, textvariable=self.onvif_password, show="•"
        )
        self.onvif_pass_entry.grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Label(ptz_box, text="Port").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Spinbox(
            ptz_box, from_=1, to=65535, textvariable=self.onvif_port, width=10
        ).grid(row=3, column=1, sticky="w", pady=5)
        ttk.Button(ptz_box, text="Uji PTZ", command=self._test_ptz).grid(
            row=4, column=1, sticky="e", pady=(8, 0)
        )

        screenshot_box = ttk.LabelFrame(outer, text="4. Screenshot", padding=10)
        screenshot_box.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        screenshot_box.columnconfigure(1, weight=1)
        ttk.Label(screenshot_box, text="Folder").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(screenshot_box, textvariable=self.screenshot_dir).grid(
            row=0, column=1, sticky="ew", pady=5
        )
        ttk.Button(screenshot_box, text="Pilih", command=self._choose_folder).grid(
            row=0, column=2, padx=(6, 0)
        )
        ttk.Checkbutton(
            screenshot_box,
            text="Screenshot otomatis",
            variable=self.auto_screenshot,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(screenshot_box, text="Interval (detik)").grid(
            row=2, column=0, sticky="w", pady=5
        )
        ttk.Spinbox(
            screenshot_box,
            from_=0.1,
            to=3600,
            increment=0.5,
            textvariable=self.screenshot_interval,
            width=12,
        ).grid(row=2, column=1, sticky="w", pady=5)

        footer = ttk.Frame(shell, padding=(14, 8, 14, 12))
        footer.grid(row=1, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Separator(footer).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(footer, textvariable=self.status, wraplength=540).grid(
            row=1, column=0, sticky="ew", padx=(0, 12)
        )
        actions = ttk.Frame(footer)
        actions.grid(row=1, column=1, sticky="e")
        ttk.Button(actions, text="Batal", command=self.root.destroy).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(actions, text="Diagnostik", command=self._show_diagnostics).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(actions, text="Simpan dan Jalankan", command=self._save).pack(
            side=tk.LEFT
        )

    def _toggle_credentials(self) -> None:
        show = "" if self.show_credentials.get() else "•"
        self.rtsp_entry.configure(show=show)
        self.onvif_pass_entry.configure(show=show)

    def _preset_id(self) -> str:
        selected_label = self.performance_preset.get()
        return next(
            (
                preset_id
                for preset_id, values in PERFORMANCE_PRESETS.items()
                if values["label"] == selected_label
            ),
            "balanced",
        )

    def _apply_performance_preset(self, _event: tk.Event | None = None) -> None:
        preset_id = self._preset_id()
        preset = PERFORMANCE_PRESETS[preset_id]
        self.device.set(str(preset["device"]))
        self.imgsz.set(int(preset["imgsz"]))
        self.status.set(
            f"{preset['label']}: device={preset['device']}, "
            f"imgsz={preset['imgsz']}, target={preset['target_fps']} FPS"
        )

    def _update_source_controls(self) -> None:
        rtsp = self.source_type.get() == "rtsp"
        self.rtsp_entry.configure(state="normal" if rtsp else "disabled")
        self.webcam_spin.configure(state="disabled" if rtsp else "normal")

    def _choose_folder(self) -> None:
        chosen = filedialog.askdirectory(
            parent=self.root,
            title="Pilih folder screenshot",
            initialdir=self.screenshot_dir.get() or str(Path.home()),
        )
        if chosen:
            self.screenshot_dir.set(chosen)

    def _current(self) -> tuple[DesktopSettings, DesktopSecrets]:
        selected_model = next(
            (model for model in self.available_models if model.name == self.model_name.get()),
            self.available_models[0],
        )
        preset_id = self._preset_id()
        preset = PERFORMANCE_PRESETS[preset_id]
        settings = replace(
            self.initial_settings,
            source_type=self.source_type.get(),
            webcam_index=int(self.webcam_index.get()),
            model_id=selected_model.id,
            performance_preset=preset_id,
            confidence=float(self.confidence.get()),
            imgsz=int(preset["imgsz"]),
            device=str(preset["device"]),
            target_fps=float(preset["target_fps"]),
            ptz_enabled=bool(self.ptz_enabled.get()),
            onvif_port=int(self.onvif_port.get()),
            screenshot_dir=self.screenshot_dir.get().strip(),
            auto_screenshot=bool(self.auto_screenshot.get()),
            auto_screenshot_interval_seconds=float(self.screenshot_interval.get()),
        )
        secrets = DesktopSecrets(
            rtsp_url=self.rtsp_url.get().strip(),
            onvif_username=self.onvif_user.get().strip(),
            onvif_password=self.onvif_password.get(),
        )
        settings.validate()
        secrets.validate_for(settings)
        return settings, secrets

    def _test_camera(self) -> None:
        frame_source = None
        try:
            settings, secrets = self._current()
            source: str | int = (
                secrets.rtsp_url if settings.source_type == "rtsp" else settings.webcam_index
            )
            if settings.source_type == "rtsp":
                os.environ.setdefault(
                    "OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp"
                )
            self.status.set(f"Menguji kamera: {redact_source(source)}")
            self.root.update_idletasks()
            frame_source = create_frame_source(
                {"source_type": "opencv", "source": source},
                source_override=str(source),
            )
            frame_source.open()
            ok, frame = frame_source.read()
            if not ok or frame is None:
                raise RuntimeError("Kamera terbuka tetapi frame belum diterima.")
            self.status.set(f"Kamera OK: {frame.shape[1]}x{frame.shape[0]}")
            messagebox.showinfo("Uji Kamera", self.status.get(), parent=self.root)
        except Exception as exc:
            self.status.set(f"Uji kamera gagal: {exc}")
            messagebox.showwarning("Uji Kamera Gagal", str(exc), parent=self.root)
        finally:
            if frame_source is not None:
                frame_source.release()

    def _test_model(self) -> None:
        try:
            from ultralytics import YOLO

            settings, _ = self._current()
            if settings.device == "0":
                import torch

                if not torch.cuda.is_available():
                    raise RuntimeError("CUDA tidak tersedia. Pilih auto atau cpu.")
            definition = model_by_id(settings.model_id)
            model_path = resolve_model_path(definition, self.paths)
            self.status.set(f"Memuat model: {definition.name}")
            self.root.update_idletasks()
            model = YOLO(str(model_path))
            self.status.set(f"Model OK: {definition.name}; kelas={model.names}")
            messagebox.showinfo("Uji Model", self.status.get(), parent=self.root)
        except Exception as exc:
            self.status.set(f"Uji model gagal: {exc}")
            messagebox.showwarning("Uji Model Gagal", str(exc), parent=self.root)

    def _show_diagnostics(self) -> None:
        try:
            settings, _ = self._current()
        except Exception:
            settings = self.initial_settings
        try:
            from .diagnostics import show_diagnostics

            show_diagnostics(self.paths, settings, parent=self.root)
        except Exception as exc:
            messagebox.showwarning("Diagnostik gagal", str(exc), parent=self.root)

    def _test_ptz(self) -> None:
        controller = None
        try:
            settings, secrets = self._current()
            if settings.source_type != "rtsp":
                raise RuntimeError("PTZ hanya tersedia untuk sumber RTSP.")
            if not settings.ptz_enabled:
                raise RuntimeError("Aktifkan PTZ terlebih dahulu.")
            environment = {
                "ONVIF_USER": secrets.onvif_username,
                "ONVIF_PASS": secrets.onvif_password,
                "ONVIF_PORT": str(settings.onvif_port),
            }
            controller = VigiPTZ(
                settings_from_source(
                    secrets.rtsp_url,
                    {
                        "onvif_port": settings.onvif_port,
                        "onvif_fallback_ports": settings.onvif_fallback_ports,
                    },
                    environ=environment,
                )
            )
            self.status.set("Menguji koneksi ONVIF/PTZ...")
            self.root.update_idletasks()
            if not controller.connect():
                raise RuntimeError(controller.last_error or "PTZ tidak dapat dihubungkan.")
            self.status.set(f"PTZ OK: {controller.endpoint}")
            messagebox.showinfo("Uji PTZ", self.status.get(), parent=self.root)
        except Exception as exc:
            self.status.set(f"Uji PTZ gagal: {exc}")
            messagebox.showwarning("Uji PTZ Gagal", str(exc), parent=self.root)
        finally:
            if controller is not None:
                controller.close()

    def _save(self) -> None:
        try:
            self.result = self._current()
        except Exception as exc:
            messagebox.showerror("Konfigurasi Tidak Valid", str(exc), parent=self.root)
            return
        self.root.destroy()

    def show(self) -> tuple[DesktopSettings, DesktopSecrets] | None:
        self.root.mainloop()
        return self.result


def show_settings_dialog(
    paths: RuntimePaths,
    settings: DesktopSettings,
    secrets: DesktopSecrets,
) -> tuple[DesktopSettings, DesktopSecrets] | None:
    return SettingsDialog(paths, settings, secrets).show()
