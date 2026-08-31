# Entok Vision

Entok Vision adalah aplikasi desktop lokal untuk deteksi awal kondisi mata entok dari
CCTV RTSP atau webcam menggunakan YOLO. Hasil AI merupakan penyaringan awal, bukan
diagnosis veteriner.

Project utama tidak memerlukan frontend web, FastAPI, MySQL, Docker, atau Node.js.
Kredensial kamera pada aplikasi terpasang disimpan terenkripsi dengan Windows DPAPI.

## Menjalankan dari source

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements\runtime.txt
Copy-Item .\.env.example .\.env
.\scripts\run_desktop.cmd
```

Untuk memvalidasi konfigurasi, model, dan satu frame kamera tanpa membuka GUI utama:

```powershell
.\scripts\check_camera.ps1
```

Kontrol GUI:

- `Q` atau `Esc`: keluar.
- `G`: buka pengaturan.
- `M`: ganti model terdaftar.
- `O`: pilih model custom.
- `C`: simpan screenshot.
- `P`: jeda.
- `T`: aktif/nonaktifkan screenshot otomatis.
- `W`, `A`, `S`, `D`: kendali PTZ bila ONVIF aktif.

## Struktur project

```text
src/entok_vision/       aplikasi desktop dan runtime computer vision
configs/                konfigurasi runtime untuk development
training/               training, validasi dataset, dan tool anotasi
data/                   data mentah/label/prepared; tidak masuk Git
experiments/            hasil training aktif dan arsip; tidak masuk Git
tests/                  test aplikasi desktop, source kamera, dan PTZ
packaging/windows/       PyInstaller dan Inno Setup
scripts/                 launcher, training, pemeriksaan kamera, dan build
requirements/            dependency runtime, training, dan development
artifacts/               hasil build dan release; tidak masuk Git
```

## Dataset dan training

Dataset training aktif:

```text
data/training/datav1_v2_combined/
```

Pemetaan kelas:

- `0`: `abnormal`
- `1`: `normal`

Jalankan preflight dan training dari root project:

```powershell
.\scripts\train.ps1 --preflight-only
.\scripts\train.ps1
```

Test set pada dataset gabungan dikunci dan hanya digunakan untuk evaluasi final setelah
checkpoint dipilih dari validation.

Evaluasi kandidat YOLO26s dan promosikan hanya jika gate lulus:

```powershell
.\scripts\evaluate_models.ps1 -Device 0
.\scripts\promote_model.ps1
```

Laporan perbandingan disimpan di `artifacts/evaluation/model_comparison.json`.
Promosi membuat `entok_yolo26s_combined.pt` sebagai model produksi dan default.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Build Windows

```powershell
.\packaging\windows\build_variant.ps1 -Variant CPU
.\packaging\windows\build_variant.ps1 -Variant GPU-CUDA124
```

Secara default tiap paket hanya membawa satu model produksi. Gunakan `-ModelSet All`
hanya untuk paket internal yang memang membutuhkan semua model.

Hasil akhir disimpan di `artifacts/release/0.2.0/`. Folder build sementara disimpan di
`artifacts/build/windows/` dan dapat dibuat ulang.

Setelah installer diunggah ke GitHub Release, buat manifest dan WebSetup kecil:

```powershell
.\packaging\windows\generate_websetup_manifest.ps1 `
  -BaseUrl "https://github.com/Marshel2727/vision-entok/releases/download/v0.2.0"
.\packaging\windows\build_websetup.ps1
```

Setiap artefak memiliki checksum SHA-256. Code signing aktif bila
`ENTOK_SIGNTOOL` dan `ENTOK_SIGNING_THUMBPRINT` sudah diatur.
