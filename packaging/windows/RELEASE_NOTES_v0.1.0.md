# Entok Vision Lite v0.1.0

Rilis percobaan pertama aplikasi desktop Windows untuk menjalankan deteksi entok
langsung dari webcam atau CCTV RTSP tanpa perlu memasang Python, Node.js, database,
atau backend web.

## Unduhan

- **Setup CPU** — pilihan yang direkomendasikan untuk instalasi biasa.
- **Portable CPU** — ekstrak seluruh ZIP, lalu jalankan `EntokVisionLite.exe`.
- **SHA-256** — gunakan file checksum untuk memeriksa integritas unduhan.

## Fitur awal

- Webcam dan CCTV RTSP.
- Tiga model YOLO bawaan.
- Pemilihan model, confidence, dan ukuran inferensi melalui wizard.
- Screenshot manual dan otomatis.
- PTZ ONVIF untuk kamera yang mendukung.
- Penyimpanan kredensial kamera menggunakan Windows DPAPI.
- Satu instance aplikasi dan log dengan rotasi otomatis.

## Catatan

- Mendukung Windows 10/11 x64.
- Rilis ini belum ditandatangani dengan sertifikat code-signing sehingga Windows
  SmartScreen dapat menampilkan peringatan penerbit tidak dikenal.
- Prediksi AI merupakan penyaringan awal dan bukan diagnosis veteriner.
- Paket GPU CUDA akan diterbitkan terpisah setelah pengujian installer selesai.
