# Tree Detection & Counting (Modul 7)

Plugin analitik Aerial Analytics Platform untuk mendeteksi tajuk pohon dari citra drone RGB,
menyaring hasilnya berdasarkan confidence, memetakan tiap pohon ke koordinat WGS84, lalu menghitung
jumlah dan kepadatan pohon.

- **Plugin ID:** `tree-detection-counting`
- **Kategori:** `tree_detection`
- **Runtime:** Python ≥ 3.10 (diuji di 3.10.11), tanpa Rust
- **Repo:** [Lambdasz/Module-7-Potencial-Men](https://github.com/Lambdasz/Module-7-Potencial-Men)
- **Kontrak antar-modul:** [CONTRACT.md](CONTRACT.md), baca ini kalau kamu dari Modul 2, 3, 9, 10, atau 11

Repo ini berdiri sendiri, terpisah dari repo core (`Aerial-Analytics-Platform`). Modul lain
berkomunikasi lewat enam file JSON, bukan lewat impor kode. Skema resminya (`schemas/`) milik repo
core, jadi validasi kontrak di bawah perlu salinan repo core.

## Status

Kedelapan fitur berjalan dan teruji, termasuk model deteksinya. Detektor default
`opencv_watershed` memakai pengolahan citra klasik: Excess Green, ambang Otsu, morfologi,
distance transform, lalu pemisahan tajuk yang berdempet. Alasannya: tidak butuh GPU, tidak
mengunduh bobot model, dan hasilnya sama untuk gambar yang sama sehingga test bisa jalan offline.

Yang perlu diketahui sebelum mempercayai angkanya:

- Detektornya klasik, bukan deep learning. Akurasinya di kebun tropis yang tajuknya rapat belum
  diukur; rencana pembanding `deepforest` ada di `requirements.txt` sebagai komentar, dan baru
  diaktifkan setelah tolok ukur presisi/recall pada gambar berlabel.
- Ini citra RGB saja. Tidak ada tinggi pohon, volume, biomassa, atau jenis pohon, dan itu sudah
  tertulis di kontrak supaya Modul 3 tidak menunggu field yang tidak akan ada.
- Koreksi manual (Feature 7) sudah ada fungsinya dan teruji, tetapi belum tersambung ke UI karena
  butuh command Tauri baru di core, jadi wewenang Modul 2.

## Struktur

```text
.
├── manifest.json            # Kontrak 1: identitas & runtime plugin
├── parameters.json          # Kontrak 2: parameter yang bisa diatur user (form Modul 2)
├── inputs.json              # Kontrak 3: input yang dibutuhkan (format gambar, metadata, AOI)
├── outputs.json             # Kontrak 4: metrik & artefak yang dihasilkan
├── execution_payload.json   # Fixture: contoh payload dari host
├── execution_result.json    # Fixture: contoh hasil yang ditulis plugin
├── main.py                  # Entrypoint CLI (lapisan I/O)
├── requirements.txt
├── CONTRACT.md              # Dokumen kontrak Modul 7 untuk modul lain
├── treedet/                 # Logika inti (fungsi murni)
│   ├── models.py            # Model data bersama (Pydantic v2, immutable)
│   ├── errors.py            # PluginExecutionError dan turunannya
│   ├── detectors.py         # Registry model deteksi + detektor opencv_watershed
│   ├── detection.py         # Fitur 1: detect_trees (+ deduplikasi antar-tile)
│   ├── counting.py          # Fitur 2: count_trees
│   ├── filtering.py         # Fitur 3: filter_by_confidence
│   ├── location.py          # Fitur 4: map_tree_locations
│   ├── area.py              # Fitur 5: count_trees_in_area (+ luas poligon)
│   ├── density.py           # Fitur 6: calculate_tree_density
│   ├── review.py            # Fitur 7: apply_review
│   ├── output.py            # Fitur 8: build_plugin_output → execution_result
│   └── pipeline.py          # Payload → fitur-fitur di atas
└── tests/                   # Unit test, test detektor, dan end-to-end (unittest)
```

## Setup

Taruh virtual environment **di luar repo**, supaya `git status` tetap bersih dan cache alat tidak
ikut masuk.

```powershell
py -3.10 -m venv $HOME\.venvs\aerial-m7
& $HOME\.venvs\aerial-m7\Scripts\Activate.ps1
pip install -r requirements.txt
pip install ruff check-jsonschema   # alat pengembangan, bukan dependensi plugin
```

Di Linux/macOS: `python3.10 -m venv ~/.venvs/aerial-m7 && source ~/.venvs/aerial-m7/bin/activate`.

## Menjalankan

```bash
# Healthcheck (dipanggil Modul 2 sebelum menampilkan plugin sebagai aktif)
python main.py --healthcheck

# Analisis
python main.py --input <execution_payload.json> --output <result.json>
```

`execution_payload.json` berisi path gambar contoh (`/absolute/path/...`), jadi kalau dijalankan
apa adanya hasilnya `status: "failure"` dengan pesan `Image not found`. Itu disengaja dan
membuktikan plugin gagal dengan rapi tanpa crash. Ganti `target.image_path` dengan gambar asli
untuk mencoba alur sukses.

## Test

```bash
python -m unittest discover -s tests -v
```

Test mencakup kedelapan fitur, termasuk kasus batas dari spesifikasi: tidak ada deteksi (`0`, bukan
error), threshold di luar 0–1 (ditolak Pydantic), luas 0 (`ZeroAreaError`), GeoJSON tidak valid
(`InvalidGeometryError`), gambar hilang (`PluginExecutionError`), format tidak didukung
(`UnsupportedFormatError`), dan gambar tidak terbaca (`PluginExecutionError`).

Test detektor memakai citra sintetis: lingkaran hijau di latar gelap, jumlahnya diketahui. Itu
membuktikan alur dan pemisahan tajuk berdempet, bukan akurasi pada foto asli.

## Lint dan format

```bash
ruff check .
ruff format --check .
```

## Validasi kontrak

Skema ada di repo core, jadi jalankan dari salinan repo core dengan path ke repo ini:

```bash
check-jsonschema --schemafile schemas/plugin.schema.json            <repo-ini>/manifest.json
check-jsonschema --schemafile schemas/parameters.schema.json        <repo-ini>/parameters.json
check-jsonschema --schemafile schemas/inputs.schema.json            <repo-ini>/inputs.json
check-jsonschema --schemafile schemas/outputs.schema.json           <repo-ini>/outputs.json
check-jsonschema --schemafile schemas/execution_payload.schema.json <repo-ini>/execution_payload.json
check-jsonschema --schemafile schemas/execution_result.schema.json  <repo-ini>/execution_result.json
```

## Desain (pemrograman fungsional)

- **Pure core, impure shell.** Semua fungsi di `treedet/` murni: input sama, output sama, tanpa
  I/O. Pengecualiannya hanya `detect_trees`, karena detektor harus membaca gambar. Baca/tulis
  file, jam, dan exit code hanya ada di `main.py`.
- **Data immutable.** Semua model Pydantic memakai `frozen=True`, dan list berbentuk `tuple`.
  Fungsi tidak pernah mengubah input; perubahan dibuat lewat `model_copy(update=...)`.
- **Waktu sebagai parameter.** `count_trees` dan `analyze` menerima `counted_at` dari luar, bukan
  membaca jam sendiri, supaya hasilnya bisa diuji dan diulang.
- **Detector sebagai fungsi.** Model deteksi adalah fungsi biasa yang disuntikkan lewat registry,
  sehingga test bisa memakai detektor palsu tanpa model sungguhan.
- **Error terisolasi.** Semua error turunan `PluginExecutionError` ditangkap `main.py`, lalu ditulis
  sebagai hasil `failure`. Plugin tidak pernah crash tanpa menulis hasil (syarat Modul 2).

## Menambah model deteksi

1. Tulis fungsi `(image_path: str, model_config: Mapping) -> Sequence[tuple[BBox, float]]` di
   `treedet/detectors.py`. Fungsi ini mengembalikan kotak tajuk dalam piksel beserta confidence 0–1.
2. Daftarkan fungsi itu di `DETECTORS`, misalnya `"deepforest": deepforest_detector`.
3. Tambahkan namanya ke `options` parameter `detector` di `parameters.json`.
4. Tambahkan paketnya ke `requirements.txt` dan ke `check_dependencies()` di `main.py`.
5. Kalau memakai GPU, sesuaikan `execution.gpu` di `manifest.json`.

Detector mengurus pembagian tile sendiri (ukurannya ada di `model_config["tile_size"]`) dan
inferensi. Deduplikasi antar-tile, filter confidence, georeferensi, dan penghitungan sudah
ditangani pipeline. Parameter baru yang dibutuhkan model harus ikut dikirim di
`pipeline.model_config_of`, kalau tidak nilainya sampai ke form tapi diabaikan diam-diam.

## Batasan yang diketahui

- Satu gambar per eksekusi (`granularity: single_image`). Belum mendukung mosaik atau GeoTIFF yang
  menyimpan transformasinya sendiri.
- Georeferensi menganggap citra nadir dan pusat gambar tepat di titik GPS, dengan pergeseran
  dihitung dari GSD lalu diputar sesuai `rotation_deg`. Error melebar pada orthomosaic atau kamera
  miring.
- Tajuk yang jaraknya lebih rapat dari separuh radius akan terbaca sebagai satu pohon, karena
  pemisahan memakai puncak distance transform.
- Tajuk yang jatuh persis di batas tile bisa dilaporkan beberapa piksel melenceng, karena
  deduplikasi menyimpan salinan yang confidence-nya paling tinggi.
- Tanpa `gsd_m` dan `rotation_deg` dari Modul 1, plugin memakai `gsd_cm` (default 3 cm/px) dan
  rotasi 0.
