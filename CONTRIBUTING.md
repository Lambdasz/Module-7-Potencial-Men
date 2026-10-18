# Cara berkontribusi di repo Modul 7

Repo ini berdiri sendiri dan hanya berisi Python. Tidak ada Rust, npm, prettier, atau clippy di
sini; gate-nya juga berbeda dari repo core.

## Sebelum push

```bash
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
```

Ketiganya harus lulus. Kalau tidak, rapikan dulu:

```bash
ruff check --fix .
ruff format .
```

## Commit dan branch

- Gaya Conventional Commits, sama seperti repo core: `feat(detector): add opencv_watershed`.
- Nama branch `<type>/<short-kebab-description>`, misalnya `feat/opencv-detector`.
- Satu commit satu maksud. PR kecil dan atomik lebih cepat direview daripada satu PR besar.
- Virtual environment dan berkas hasil plugin tidak ikut di-commit (lihat `.gitignore`).

## Bahasa

Kode, nama variabel, dan komentar ditulis Inggris supaya konsisten dengan repo core. Dokumen untuk
tim (README, CONTRACT) ditulis Indonesia.

## Mengubah kontrak

`parameters.json`, `inputs.json`, dan `outputs.json` dibaca modul lain. Menambah parameter berarti
form Modul 2 ikut berubah, dan menambah metrik atau artefak berarti dashboard Modul 11 ikut berubah.
Ajukan dulu, jangan dikirim mendadak di tengah sprint:

- Parameter baru: tambahkan di `parameters.json`, kirim ke detektor lewat
  `pipeline.model_config_of` kalau model membutuhkannya, dan sebut di PR bahwa form Modul 2 ikut
  berubah.
- Metrik atau artefak baru: ubah `outputs.json` dan `treedet/output.py`, lalu koordinasikan dengan
  Modul 11 sebelum di-merge.
- Hal yang menuntut command Tauri atau halaman baru di core adalah wewenang Modul 2. Tulis
  permintaannya sebagai issue, jangan dikerjakan dari repo ini.
