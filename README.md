# Entok Vision

Sistem lokal/LAN untuk deteksi kondisi mata entok menggunakan FastAPI, YOLO, MySQL,
dan dashboard Next.js. Prediksi AI adalah penyaringan awal, bukan diagnosis veteriner.

## Entok Vision Lite untuk Windows

Entok Vision Lite adalah aplikasi desktop mandiri dari `back_end/ai/cctv_gui.py`.
Versi ini dapat dipakai untuk CCTV RTSP atau webcam tanpa memasang Python, database,
backend web, maupun Node.js.

Unduh versi terbaru dari [GitHub Releases](https://github.com/Marshel2727/vision-entok/releases/latest):

- `EntokVisionLite-0.1.0-Windows-x64-CPU-Setup.exe`: pilihan utama; instal seperti aplikasi Windows biasa.
- `EntokVisionLite-0.1.0-Windows-x64-CPU-Portable.zip`: ekstrak seluruh ZIP, lalu jalankan `EntokVisionLite.exe`; jangan jalankan dari dalam ZIP.
- File `.sha256`: checksum untuk memastikan unduhan tidak rusak atau berubah.

Rilis awal `v0.1.0` hanya memublikasikan varian CPU agar pemasangan dan pengujian
pertama lebih sederhana. Source untuk build GPU CUDA 12.4 sudah disiapkan, tetapi
paket binernya akan diterbitkan pada rilis terpisah setelah pengujian installer selesai.

Pada pemakaian pertama, wizard akan meminta sumber video, model, perangkat pemrosesan,
opsi PTZ ONVIF, dan folder screenshot. Kredensial kamera disimpan terenkripsi dengan
Windows DPAPI untuk akun Windows yang sedang digunakan.

Kontrol utama ketika jendela deteksi aktif:

- `Q`: keluar.
- `G`: buka pengaturan kembali.
- `M`: ganti model.
- `S`: simpan screenshot manual.
- Tombol panah dan `+`/`-`: kendali PTZ apabila ONVIF aktif.

Versi `0.1.0` adalah build uji yang belum memiliki sertifikat code-signing komersial,
sehingga Windows SmartScreen dapat menampilkan peringatan penerbit tidak dikenal.
Periksa bahwa file berasal dari repositori ini dan cocokkan SHA-256 sebelum menjalankan.

### Build Desktop Lite dari source

Jalankan PowerShell dari root project:

```powershell
.\packaging\desktop_lite\build_variant.ps1 -Variant CPU
# Opsional/eksperimental untuk pengembangan lokal:
.\packaging\desktop_lite\build_variant.ps1 -Variant GPU-CUDA124
```

Hasil build disimpan di `dist/desktop-lite/`. Build memerlukan Python 3.12/3.13 x64
dan Inno Setup 7 atau Inno Setup 6 untuk menghasilkan `Setup.exe`.

## Dataset

Folder dataset mempunyai dua fungsi yang berbeda:

- `back_end/ai/dataset/images/` untuk penyimpanan awal foto mentah yang belum dilabeli.
- `back_end/ai/dataset/labels/` untuk kumpulan dataset yang sudah dilabeli. Setiap versi
  dataset di dalamnya tetap berupa satu paket YOLO lengkap dengan folder gambar dan anotasi.

Dataset training aktif berada di `back_end/ai/dataset/labels/datav1/`. Jalankan validasi
sebelum training:

```powershell
.\back_end\venv\Scripts\python.exe .\back_end\ai\dataset_preflight.py .\back_end\ai\configs\data.yaml --expected-names abnormal normal
```

Hasil canonical yang sebelumnya memisahkan gambar dan label di tingkat atas telah
diamankan di `back_end/ai/dataset_archive/generated_canonical_v1/` dan tidak digunakan
sebagai dataset training aktif.

## Persiapan

1. Aktifkan MySQL dan buat database `cv_entok_db`.
2. Salin konfigurasi dari `back_end/.env.example` dan `front_end/.env.example` bila diperlukan.
3. Jalankan migrasi:

```powershell
.\scripts\migrate.ps1
```

4. Buat admin pertama:

```powershell
cd back_end
.\venv\Scripts\python.exe -m scripts.create_admin --username admin --name "Administrator"
```

5. Jalankan aplikasi:

```powershell
.\scripts\start_all.ps1
```

Dashboard tersedia di `http://localhost:3000`. Perangkat lain pada LAN dapat membuka
`http://IP-PC:3000` setelah port 3000 diizinkan pada Windows Firewall.

## Perintah pengembangan

```powershell
cd back_end
.\venv\Scripts\python.exe -m pytest

cd ..\front_end
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

## Kamera

Admin dapat menyimpan satu konfigurasi webcam/OpenCV, RTSP, FFmpeg/MediaMTX, screen
capture, atau ADB melalui halaman `/admin/camera`. Jalankan uji koneksi sebelum
mengaktifkan runtime. Validasi mock tidak menggantikan pengujian kamera fisik.
