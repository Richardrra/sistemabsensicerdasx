# 🧑‍💻 Sistem Cerdas Absensi Wajah (Streamlit + Teachable Machine)

Aplikasi absensi berbasis pengenalan wajah menggunakan model AI yang
dilatih di **Google Teachable Machine**, dijalankan dengan **Streamlit**.

## ✨ Fitur
- Absen via kamera langsung dari browser (`st.camera_input`)
- Pengenalan wajah otomatis pakai model Teachable Machine (.h5)
- Pencatatan otomatis ke CSV (nama, tanggal, jam, tingkat keyakinan)
- Anti duplikat: satu orang hanya bisa absen 1x per hari
- Halaman riwayat absensi dengan filter nama/tanggal + unduh CSV
- Ambang batas keyakinan (confidence threshold) bisa diatur di sidebar

## 📁 Struktur Folder
```
absensi-wajah-cerdas/
├── app.py               # Aplikasi utama Streamlit
├── requirements.txt      # Daftar dependensi Python
├── model/
│   ├── keras_model.h5    # ⬅️ Taruh file model di sini (dari Teachable Machine)
│   └── labels.txt        # ⬅️ Taruh file label di sini
└── data/
    └── attendance.csv    # Dibuat otomatis saat pertama kali absen
```

## 🚀 Langkah 1: Latih Model di Teachable Machine

1. Buka https://teachablemachine.withgoogle.com/train/image
2. Pilih **Standard image model**
3. Buat satu **Class** untuk setiap orang yang ingin dikenali, misalnya:
   - `Budi`
   - `Siti`
   - `Andi`
4. Untuk tiap kelas, klik **Webcam** dan ambil banyak foto wajah orang
   tersebut dari berbagai sudut/pencahayaan (minimal 50-100 foto per orang
   agar akurat).
5. **Penting:** tambahkan satu kelas ekstra bernama `Tidak_Dikenal` yang
   isinya foto acak (latar ruangan kosong, wajah orang lain, dll) supaya
   model tidak asal menebak saat tidak ada wajah yang cocok.
6. Klik **Train Model**, tunggu sampai selesai.
7. Setelah training selesai, klik **Export Model**.
8. Pilih tab **Tensorflow** → pilih **Keras** → klik **Download my model**.
9. Ekstrak file zip yang didownload, di dalamnya ada:
   - `keras_model.h5`
   - `labels.txt`
10. Salin kedua file tersebut ke folder `model/` pada project ini.

## 🚀 Langkah 2: Install & Jalankan Aplikasi

```bash
# (opsional) buat virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# install dependensi
pip install -r requirements.txt

# jalankan aplikasi
streamlit run app.py
```

Aplikasi akan terbuka otomatis di browser pada `http://localhost:8501`.

## 🖥️ Cara Pakai
1. Buka tab **📸 Absen Sekarang**
2. Izinkan akses kamera saat diminta browser
3. Arahkan wajah ke kamera, klik tombol ambil foto
4. Sistem akan menampilkan nama yang dikenali beserta persentase keyakinan
5. Jika keyakinan di atas ambang batas, absensi otomatis tercatat
6. Cek hasil rekap di tab **📊 Riwayat Absensi**

## ⚠️ Catatan Kompatibilitas
Model `.h5` dari Teachable Machine kadang memunculkan error seperti:
```
TypeError: __init__() got an unexpected keyword argument 'groups'
```
Ini terjadi karena perbedaan versi TensorFlow. Kode `app.py` pada project
ini **sudah menangani masalah tersebut secara otomatis**. Jika error masih
muncul, coba install versi TensorFlow yang disarankan:
```bash
pip install "tensorflow==2.12.0"
```

## 🔧 Penyesuaian Lanjutan (opsional)
- Ubah `IMG_SIZE` di `app.py` jika model dilatih dengan ukuran gambar berbeda
  (default Teachable Machine adalah 224x224).
- Ubah nama kelas "penolak" di kode (`tidak_dikenal`, `unknown`, dst.) sesuai
  nama kelas yang kamu pakai saat training.
- Untuk deployment online, gunakan [Streamlit Community Cloud](https://streamlit.io/cloud)
  — cukup upload project ini ke GitHub lalu hubungkan ke Streamlit Cloud.
  Catatan: kamera hanya berfungsi jika situs diakses via HTTPS.
