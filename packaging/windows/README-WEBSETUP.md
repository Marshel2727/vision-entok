# WebSetup Entok Vision Lite

WebSetup adalah downloader kecil untuk memilih paket CPU atau GPU. File parsial
disimpan di `%LOCALAPPDATA%\EntokVisionLite\downloads`, dapat dilanjutkan dengan
HTTP Range, lalu diverifikasi ukuran dan SHA-256 sebelum installer dijalankan.

Urutan rilis:

1. Build installer CPU dan GPU.
2. Generate `websetup-manifest.json` menggunakan URL aset rilis GitHub.
3. Upload installer dan manifest ke GitHub Release.
4. Build dan code-sign WebSetup.

URL default WebSetup menunjuk aset `latest/download/websetup-manifest.json` pada
repository `Marshel2727/vision-entok`.
