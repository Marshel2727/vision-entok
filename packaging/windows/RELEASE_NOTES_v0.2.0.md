# Entok Vision Lite v0.2.0

Entok Vision Lite v0.2.0 berfokus pada pemantauan CCTV berlatensi rendah,
kestabilan koneksi, model deteksi yang lebih baik, dan distribusi Windows yang
lebih mudah digunakan.

## Pilih paket yang sesuai

| Paket | Disarankan untuk |
| --- | --- |
| **WebSetup** | Pengguna umum; pilih CPU atau GPU saat dijalankan. |
| **CPU Setup** | Komputer tanpa GPU NVIDIA atau instalasi paling kompatibel. |
| **CPU Portable** | Penggunaan tanpa instalasi. Ekstrak seluruh ZIP dahulu. |
| **GPU CUDA 12.4 Setup** | Komputer Windows dengan GPU NVIDIA dan driver terbaru. |

Untuk paket GPU, unduh `Setup.exe` dan `Setup-1.bin`, simpan keduanya di folder
yang sama, lalu jalankan `Setup.exe`.

## Yang baru

- Reader CCTV berjalan di background dan hanya mempertahankan frame terbaru.
- Frame lama dibuang agar tampilan tidak tertinggal saat inferensi lebih lambat
  daripada FPS kamera.
- Preset **Low Latency**, **Mode Hemat**, **Mode Seimbang**, dan
  **Mode Akurasi Tinggi**.
- HUD tiga baris menampilkan status kamera, CPU/CUDA, FPS inferensi, latensi,
  model aktif, jumlah normal/abnormal, status PTZ, dan waktu reconnect.
- Reconnect otomatis bertahap serta perintah reconnect manual tanpa membekukan
  loop tampilan.
- Halaman diagnostik dengan versi aplikasi/model, checksum, CUDA/GPU, resolusi,
  FPS, lokasi konfigurasi/log, serta ekspor laporan JSON.
- Pemeriksaan pembaruan melalui manifest rilis.
- Paket Production hanya membawa satu model aktif sehingga paket CPU lebih kecil.
- WebSetup mendukung pilihan CPU/GPU, resume unduhan, retry, pemeriksaan ukuran,
  dan validasi SHA-256 sebelum installer dijalankan.

## Model produksi baru

Model default adalah **YOLO26s Gabungan** dengan SHA-256:

```text
28b85511fa8e03fba6f88c84aba298896941e2ed0e22478117504f0c4b7dafdf
```

Evaluasi dilakukan pada split `test` terkunci dengan `imgsz=960`:

| Metrik | Model sebelumnya | YOLO26s Gabungan |
| --- | ---: | ---: |
| Recall abnormal | 0.94118 | 0.94118 |
| Precision abnormal | 0.68676 | 0.86299 |
| mAP50-95 abnormal | 0.62140 | 0.89360 |
| mAP50-95 keseluruhan | 0.39008 | 0.59440 |

Gate promosi lulus: recall abnormal dipertahankan dan mAP50-95 keseluruhan naik
sebesar `0.20431`.

## Verifikasi unduhan

Setiap aset memiliki file `.sha256`. Contoh pemeriksaan di PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\EntokVisionLite-0.2.0-WebSetup.exe
```

Bandingkan hasilnya dengan isi file `.sha256` yang bersesuaian.

## Persyaratan dan catatan

- Windows 10/11 x64.
- Paket GPU memerlukan GPU NVIDIA serta driver yang kompatibel.
- Build ini belum ditandatangani sertifikat komersial; Windows SmartScreen dapat
  menampilkan peringatan penerbit tidak dikenal.
- GPU Portable tidak diterbitkan karena ukurannya melampaui batas per-file GitHub
  Release; gunakan GPU Setup atau WebSetup.
- Validasi pada instalasi Windows bersih dan CCTV fisik tetap diperlukan sebelum
  rilis dinyatakan tervalidasi penuh.
- Prediksi AI merupakan alat penyaringan awal, bukan diagnosis veteriner.
