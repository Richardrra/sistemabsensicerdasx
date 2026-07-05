
import os
import hashlib
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageOps

# ------------------------------------------------------------------
# KONFIGURASI
# ------------------------------------------------------------------
MODEL_PATH = "model/keras_model.h5"
LABELS_PATH = "model/labels.txt"
ATTENDANCE_PATH = "data/attendance.csv"
DB_PATH = "data/mahasiswa.db"
IMG_SIZE = (224, 224)
IGNORED_LABELS = ("tidak_dikenal", "unknown", "background", "noise")

# --- Kredensial Admin (GANTI sebelum dipakai serius!) ---
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"  # ganti password ini
ADMIN_PASSWORD_HASH = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()

st.set_page_config(
    page_title="Absensi Wajah Cerdas",
    page_icon="",
    layout="centered",
)

os.makedirs("data", exist_ok=True)


# ------------------------------------------------------------------
# DATABASE MAHASISWA (SQLite)
# ------------------------------------------------------------------
def apply_custom_css(css_path="assets/style.css"):
    """Memuat dan menyuntikkan file CSS eksternal ke aplikasi Streamlit."""
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
    else:
        st.warning(f"File styling tidak ditemukan: {css_path}")

def tambah_label_diabaikan(label):
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO label_diabaikan (label_wajah) VALUES (?)", (label,)
    )
    conn.commit()
    conn.close()


def hapus_label_diabaikan(label):
    conn = get_db_connection()
    conn.execute("DELETE FROM label_diabaikan WHERE label_wajah = ?", (label,))
    conn.commit()
    conn.close()


def get_labels_diabaikan():
    conn = get_db_connection()
    rows = [r["label_wajah"] for r in conn.execute("SELECT label_wajah FROM label_diabaikan").fetchall()]
    conn.close()
    return rows
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mahasiswa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nim TEXT UNIQUE NOT NULL,
            nama TEXT NOT NULL,
            kelas TEXT,
            label_wajah TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'Aktif',
            keterangan TEXT DEFAULT 'Baru',
            tanggal_daftar TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS label_diabaikan (
            label_wajah TEXT PRIMARY KEY
        )
        """
    )
    conn.commit()
    conn.close()



def sync_labels_to_db(labels):
    conn = get_db_connection()
    existing_labels = [
        r["label_wajah"] for r in conn.execute("SELECT label_wajah FROM mahasiswa").fetchall()
    ]
    ignored_labels = get_labels_diabaikan()
    for label in labels:
        if label.lower() in IGNORED_LABELS:
            continue
        if label in ignored_labels:
            continue
        if label not in existing_labels:
            placeholder_nim = f"TM-{label}"
            try:
                conn.execute(
                    """INSERT INTO mahasiswa
                       (nim, nama, kelas, label_wajah, status, keterangan, tanggal_daftar)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (placeholder_nim, label, "-", label, "Aktif", "Baru",
                     datetime.now().strftime("%Y-%m-%d")),
                )
            except sqlite3.IntegrityError:
                pass
    conn.commit()
    conn.close()


def get_all_mahasiswa() -> pd.DataFrame:
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM mahasiswa ORDER BY id DESC", conn)
    conn.close()
    return df


def get_mahasiswa_by_label(label: str):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM mahasiswa WHERE label_wajah = ?", (label,)).fetchone()
    conn.close()
    return row


def add_mahasiswa(nim, nama, kelas, label_wajah, status, keterangan):
    conn = get_db_connection()
    try:
        conn.execute(
            """INSERT INTO mahasiswa (nim, nama, kelas, label_wajah, status, keterangan, tanggal_daftar)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (nim, nama, kelas, label_wajah, status, keterangan,
             datetime.now().strftime("%Y-%m-%d")),
        )
        conn.commit()
        return True, "Data mahasiswa berhasil ditambahkan."
    except sqlite3.IntegrityError:
        return False, f"NIM '{nim}' atau label wajah '{label_wajah}' sudah dipakai."
    finally:
        conn.close()


def update_mahasiswa(id_, nim, nama, kelas, label_wajah, status, keterangan):
    conn = get_db_connection()
    try:
        conn.execute(
            """UPDATE mahasiswa
               SET nim=?, nama=?, kelas=?, label_wajah=?, status=?, keterangan=?
               WHERE id=?""",
            (nim, nama, kelas, label_wajah, status, keterangan, id_),
        )
        conn.commit()
        return True, "Data mahasiswa berhasil diperbarui."
    except sqlite3.IntegrityError:
        return False, f"NIM '{nim}' atau label wajah '{label_wajah}' sudah dipakai mahasiswa lain."
    finally:
        conn.close()


def delete_mahasiswa(id_):
    conn = get_db_connection()
    row = conn.execute("SELECT label_wajah FROM mahasiswa WHERE id=?", (id_,)).fetchone()
    if row:
        tambah_label_diabaikan(row["label_wajah"])
    conn.execute("DELETE FROM mahasiswa WHERE id=?", (id_,))
    conn.commit()
    conn.close()

# ------------------------------------------------------------------
# AUTH ADMIN
# ------------------------------------------------------------------
def check_login(username: str, password: str) -> bool:
    hashed_input = hashlib.sha256(password.encode()).hexdigest()
    return username == ADMIN_USERNAME and hashed_input == ADMIN_PASSWORD_HASH


def login_form():
    st.subheader("Login Admin")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Masuk")

        if submitted:
            if check_login(username, password):
                st.session_state["is_admin"] = True
                st.success("Login berhasil!")
                st.rerun()
            else:
                st.error("Username atau password salah.")


def logout_button():
    if st.button("Logout"):
        st.session_state["is_admin"] = False
        st.rerun()


# ------------------------------------------------------------------
# FUNGSI PENGENALAN WAJAH (MODEL)
# ------------------------------------------------------------------
@st.cache_resource(show_spinner="Memuat model AI...")
def load_face_model():
    from tensorflow.keras.layers import DepthwiseConv2D
    from tensorflow.keras.models import load_model

    class PatchedDepthwiseConv2D(DepthwiseConv2D):
        def __init__(self, *args, **kwargs):
            kwargs.pop("groups", None)
            super().__init__(*args, **kwargs)

    try:
        model = load_model(MODEL_PATH, compile=False)
    except TypeError:
        model = load_model(
            MODEL_PATH,
            compile=False,
            custom_objects={"DepthwiseConv2D": PatchedDepthwiseConv2D},
        )

    with open(LABELS_PATH, "r", encoding="utf-8") as f:
        raw_labels = [line.strip() for line in f.readlines() if line.strip()]
    labels = [lbl.split(" ", 1)[1] if " " in lbl else lbl for lbl in raw_labels]

    return model, labels


def preprocess_image(image: Image.Image) -> np.ndarray:
    image = ImageOps.fit(image.convert("RGB"), IMG_SIZE, Image.Resampling.LANCZOS)
    image_array = np.asarray(image, dtype=np.float32)
    normalized_array = (image_array / 127.5) - 1
    return np.expand_dims(normalized_array, axis=0)


def predict(model, labels, image: Image.Image):
    data = preprocess_image(image)
    prediction = model.predict(data, verbose=0)[0]
    idx = int(np.argmax(prediction))
    return labels[idx], float(prediction[idx])


# ------------------------------------------------------------------
# FUNGSI ABSENSI (CSV)
# ------------------------------------------------------------------
def hapus_absen_by_index(indices):
    df = load_attendance()
    df = df.drop(index=indices).reset_index(drop=True)
    save_attendance(df)


def hapus_semua_absen():
    save_attendance(pd.DataFrame(columns=ATTENDANCE_COLUMNS))
ATTENDANCE_COLUMNS = ["NIM", "Nama", "Kelas", "Tanggal", "Jam", "Keyakinan"]


def load_attendance() -> pd.DataFrame:
    if os.path.exists(ATTENDANCE_PATH):
        df = pd.read_csv(ATTENDANCE_PATH)
        for col in ATTENDANCE_COLUMNS:
            if col not in df.columns:
                df[col] = "-"
        return df[ATTENDANCE_COLUMNS]
    return pd.DataFrame(columns=ATTENDANCE_COLUMNS)


def save_attendance(df: pd.DataFrame):
    df.to_csv(ATTENDANCE_PATH, index=False)


def already_checked_in_today(df: pd.DataFrame, nim: str, nama: str) -> bool:
    if df.empty:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    if nim and nim != "-":
        return ((df["NIM"] == nim) & (df["Tanggal"] == today)).any()
    return ((df["Nama"] == nama) & (df["Tanggal"] == today)).any()


def catat_absen(nim, nama, kelas, confidence):
    df = load_attendance()
    now = datetime.now()
    new_row = {
        "NIM": nim,
        "Nama": nama,
        "Kelas": kelas,
        "Tanggal": now.strftime("%Y-%m-%d"),
        "Jam": now.strftime("%H:%M:%S"),
        "Keyakinan": f"{confidence * 100:.1f}%",
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_attendance(df)


# ------------------------------------------------------------------
# WIDGET ABSEN (dipakai di Dashboard)
# ------------------------------------------------------------------
def render_absen_widget(model, labels, threshold, key_prefix="dash"):
    img_file = st.camera_input("Arahkan wajah ke kamera lalu klik ambil foto", key=f"{key_prefix}_cam")

    if img_file is not None:
        image = Image.open(img_file)
        with st.spinner("Mengenali wajah..."):
            name, confidence = predict(model, labels, image)

        col1, col2 = st.columns([1, 1.3])
        with col1:
            st.image(image, caption="Foto yang diambil", use_container_width=True)

        with col2:
            st.metric("Prediksi", name, f"{confidence * 100:.1f}% yakin")

            if name.lower() in IGNORED_LABELS:
                st.error("Wajah tidak dikenali sebagai anggota terdaftar.")
                return

            if confidence < threshold:
                st.warning(
                    f"Keyakinan sistem masih rendah ({confidence * 100:.1f}%). "
                    "Coba ambil foto ulang dengan pencahayaan lebih baik."
                )
                return

            mhs = get_mahasiswa_by_label(name)
            if mhs is None:
                st.error(
                    "Wajah dikenali sistem tetapi **belum terdaftar** di data mahasiswa. "
                    "Absensi tidak dicatat. Minta admin melengkapi data di tab Admin terlebih dahulu."
                )
                return

            nim_val, nama_val, kelas_val = mhs["nim"], mhs["nama"], mhs["kelas"]
            if mhs["status"] == "Nonaktif":
                st.error(f"**{nama_val}** berstatus Nonaktif dan tidak dapat melakukan absensi.")
                return

            df = load_attendance()
            if already_checked_in_today(df, nim_val, nama_val):
                st.warning(f"**{nama_val}** sudah tercatat absen hari ini.")
            else:
                catat_absen(nim_val, nama_val, kelas_val, confidence)
                st.success(f"Absensi berhasil dicatat untuk **{nama_val}**! ✅")
               


# ------------------------------------------------------------------
# APLIKASI UTAMA
# ------------------------------------------------------------------
def main():
    init_db()
    apply_custom_css()   # <-- pastikan baris ini ada

    if "is_admin" not in st.session_state:
        st.session_state["is_admin"] = False

    st.markdown(
        """
        <div style="text-align:center; padding: 10px 0 24px 0;">
            <h1 style="margin-bottom:0;">🧑‍💻 Sistem Cerdas Absensi Wajah</h1>
            <p style="color:#6b7280; font-size:16px; margin-top:4px;">
                Dibangun dengan Streamlit + AI Teachable Machine
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("⚙️ Pengaturan")
        threshold = st.slider(
            "Ambang batas keyakinan (confidence)",
            min_value=0.5, max_value=0.99, value=0.85, step=0.01,
        )
        st.markdown("---")
        
    if not (os.path.exists(MODEL_PATH) and os.path.exists(LABELS_PATH)):
        st.error("Model belum ditemukan di folder `model/`.")
        st.info("Taruh **keras_model.h5** dan **labels.txt** di folder `model/`.")
        st.stop()

    model, labels = load_face_model()
    sync_labels_to_db(labels)  # sinkron otomatis data mahasiswa dari Teachable Machine

    tab_dashboard, tab_riwayat, tab_admin = st.tabs(
        [" Dashboard", " Riwayat Absensi", " Admin"]
    )

    # ---------------- TAB DASHBOARD ----------------
    with tab_dashboard:
        df_mhs = get_all_mahasiswa()
        df_absen = load_attendance()
        today = datetime.now().strftime("%Y-%m-%d")
        absen_hari_ini = df_absen[df_absen["Tanggal"] == today] if not df_absen.empty else df_absen

        total_mhs = len(df_mhs[df_mhs["status"] == "Aktif"]) if not df_mhs.empty else 0
        total_hadir = len(absen_hari_ini)
        total_belum = max(total_mhs - total_hadir, 0)

        c1, c2, c3 = st.columns(3)
        c1.metric("Mahasiswa Aktif", total_mhs)
        c2.metric("Hadir Hari Ini", total_hadir)
        c3.metric(" Belum Absen", total_belum)

        st.markdown("---")
        st.subheader(" Absen Sekarang")
        render_absen_widget(model, labels, threshold, key_prefix="dashboard")

        st.markdown("---")
        st.subheader(" Statistik Kehadiran (7 Hari Terakhir)")
        if df_absen.empty:
            st.info("Belum ada data absensi untuk ditampilkan.")
        else:
            last_7_days = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
            counts = [len(df_absen[df_absen["Tanggal"] == d]) for d in last_7_days]
            chart_df = pd.DataFrame({"Tanggal": last_7_days, "Jumlah Hadir": counts}).set_index("Tanggal")
            st.bar_chart(chart_df)

        if total_belum > 0 and not df_mhs.empty:
            with st.expander(f"Lihat {total_belum} mahasiswa yang belum absen hari ini"):
                hadir_nim = absen_hari_ini["NIM"].tolist() if not absen_hari_ini.empty else []
                belum_df = df_mhs[
                    (df_mhs["status"] == "Aktif") & (~df_mhs["nim"].isin(hadir_nim))
                ][["nim", "nama", "kelas"]]
                st.dataframe(belum_df, use_container_width=True, hide_index=True)

    # ---------------- TAB RIWAYAT ----------------
    with tab_riwayat:
        st.subheader("Riwayat Absensi")
        df = load_attendance()

        if df.empty:
            st.info("Belum ada data absensi yang tercatat.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                nama_pilihan = st.selectbox(
                    "Filter berdasarkan nama",
                    ["Semua"] + sorted(df["Nama"].unique().tolist()),
                )
            with col2:
                tanggal_pilihan = st.date_input("Filter berdasarkan tanggal", value=None)

            filtered = df.copy()
            if nama_pilihan != "Semua":
                filtered = filtered[filtered["Nama"] == nama_pilihan]
            if tanggal_pilihan:
                filtered = filtered[filtered["Tanggal"] == tanggal_pilihan.strftime("%Y-%m-%d")]

            st.dataframe(filtered, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇Unduh Data (CSV)",
                data=filtered.to_csv(index=False).encode("utf-8"),
                file_name="riwayat_absensi.csv",
                mime="text/csv",
            )
            st.caption(f"Total rekap: {len(df)} data absensi")

    # ---------------- TAB ADMIN (CRUD MAHASISWA) ----------------
    with tab_admin:
        if not st.session_state["is_admin"]:
            login_form()
        else:
            st.subheader(" Kelola Data Mahasiswa")
            logout_button()
            st.caption(
                "Data mahasiswa otomatis tersinkron dari `labels.txt` Teachable Machine. "
                "Lengkapi NIM & Kelas untuk mahasiswa baru di bawah ini."
            )
            st.markdown("---")

            sub_tambah, sub_lihat, sub_riwayat = st.tabs(
                [" Tambah Manual", " Data Mahasiswa", "Kelola Riwayat Absen"]
            )

            # --- TAMBAH MANUAL (opsional, jika perlu tambah di luar sinkron label) ---
            with sub_tambah:
                with st.form("form_tambah", clear_on_submit=True):
                    nim = st.text_input("NIM")
                    nama = st.text_input("Nama Lengkap")
                    kelas = st.text_input("Kelas / Jurusan")
                    label_wajah = st.selectbox(
                        "Label Wajah (harus sama persis dengan nama kelas di Teachable Machine)",
                        labels,
                    )
                    status = st.selectbox("Status", ["Aktif", "Nonaktif"])
                    keterangan = st.selectbox("Keterangan", ["Baru", "Lama"])
                    submit_tambah = st.form_submit_button("Simpan")

                    if submit_tambah:
                        if not nim or not nama:
                            st.error("NIM dan Nama wajib diisi.")
                        else:
                            ok, msg = add_mahasiswa(nim, nama, kelas, label_wajah, status, keterangan)
                            st.success(msg) if ok else st.error(msg)

            # --- LIHAT / EDIT / HAPUS ---
            with sub_lihat:
                df_mhs = get_all_mahasiswa()

                if df_mhs.empty:
                    st.info("Belum ada data mahasiswa.")
                else:
                    st.dataframe(df_mhs, use_container_width=True, hide_index=True)
                    st.markdown("---")
                    st.markdown("###  Edit / Hapus Data")
                    st.caption(
                        "Data dengan NIM berawalan `TM-` artinya baru tersinkron otomatis "
                        "dari label Teachable Machine dan belum dilengkapi datanya."
                    )

                    pilihan = st.selectbox(
                        "Pilih mahasiswa (berdasarkan NIM - Nama)",
                        df_mhs.apply(lambda r: f"{r['id']} | {r['nim']} - {r['nama']}", axis=1),
                    )
                    selected_id = int(pilihan.split(" | ")[0])
                    row = df_mhs[df_mhs["id"] == selected_id].iloc[0]
                    # --- HAPUS RIWAYAT ABSEN ---
            with sub_riwayat:
                df_absen = load_attendance()

                if df_absen.empty:
                    st.info("Belum ada data riwayat absensi.")
                else:
                    st.dataframe(df_absen, use_container_width=True)
                    st.markdown("---")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("#### Hapus Baris Tertentu")
                        opsi = df_absen.apply(
                            lambda r: f"{r.name} | {r['Nama']} - {r['Tanggal']} {r['Jam']}", axis=1
                        )
                        pilihan_hapus = st.multiselect("Pilih data yang ingin dihapus", opsi)

                        if st.button(" Hapus Data Terpilih", disabled=len(pilihan_hapus) == 0):
                            indices = [int(p.split(" | ")[0]) for p in pilihan_hapus]
                            hapus_absen_by_index(indices)
                            st.success(f"{len(indices)} data riwayat berhasil dihapus.")
                            st.rerun()

                    with col2:
                        st.markdown("#### Hapus Semua Riwayat")
                        st.warning("Tindakan ini akan menghapus SELURUH riwayat absensi.")
                        konfirmasi = st.checkbox("Saya yakin ingin menghapus semua riwayat")
                        if st.button(" Hapus Semua", disabled=not konfirmasi, type="secondary"):
                            hapus_semua_absen()
                            st.success("Seluruh riwayat absensi berhasil dihapus.")
                            st.rerun()
                    with st.form("form_edit"):
                        nim_e = st.text_input("NIM", value=row["nim"])
                        nama_e = st.text_input("Nama Lengkap", value=row["nama"])
                        kelas_e = st.text_input("Kelas / Jurusan", value=row["kelas"] or "")
                        label_e = st.selectbox(
                            "Label Wajah", labels,
                            index=labels.index(row["label_wajah"]) if row["label_wajah"] in labels else 0,
                        )
                        status_e = st.selectbox(
                            "Status", ["Aktif", "Nonaktif"],
                            index=0 if row["status"] == "Aktif" else 1,
                        )
                        keterangan_e = st.selectbox(
                            "Keterangan", ["Baru", "Lama"],
                            index=0 if row["keterangan"] == "Baru" else 1,
                        )

                        col_a, col_b = st.columns(2)
                        with col_a:
                            submit_edit = st.form_submit_button(" Update")
                        with col_b:
                            submit_hapus = st.form_submit_button("Hapus", type="secondary")

                        if submit_edit:
                            ok, msg = update_mahasiswa(
                                selected_id, nim_e, nama_e, kelas_e, label_e, status_e, keterangan_e
                            )
                            st.success(msg) if ok else st.error(msg)
                            st.rerun()

                        if submit_hapus:
                            delete_mahasiswa(selected_id)
                            st.warning(f"Data mahasiswa '{row['nama']}' dihapus.")
                            st.rerun()
if __name__ == "__main__":
    main()