import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Pengelompokan Paket Toko Otomatis", layout="wide")

st.title("🚚 Aplikasi Pengelompokan Paket Distribusi Toko")
st.write("Aplikasi ini secara otomatis mengelompokkan toko ke dalam armada mobil berdasarkan aturan rute, urutan picking, rit, dan kapasitas volume.")

# Sidebar Configuration
st.sidebar.header("⚙️ Pengaturan Parameter")

max_volume = st.sidebar.slider(
    "Kapasitas Maksimal Mobil (m³)",
    min_value=1.0,
    max_value=15.0,
    value=9.0,
    step=0.5
)

min_stores = st.sidebar.number_input(
    "Jumlah Toko Minimal per Mobil",
    min_value=1,
    max_value=5,
    value=2
)

max_stores = st.sidebar.number_input(
    "Jumlah Toko Maksimal per Mobil",
    min_value=2,
    max_value=10,
    value=4
)

max_picking_diff = st.sidebar.slider(
    "Batas Toleransi Selisih Urutan Picking",
    min_value=5,
    max_value=50,
    value=15,
    step=1
)

uploaded_file = st.sidebar.file_uploader(
    "Unggah File Data Toko (.csv)",
    type=["csv"]
)

def process_data(df, max_vol, min_st, max_st, max_pick_diff):

    # Copy dataframe
    df = df.copy()

    # Rapikan nama kolom
    df.columns = [c.strip() for c in df.columns]

    # =========================
    # CLEANING DATA NUMERIC
    # =========================

    numeric_cols = [
        'Volume Container(m3)',
        'Volume DOS (m3)',
        'TOTAL (m3)',
        'URUT PICKING',
        'RIT',
        'GRUP'
    ]

    for col in numeric_cols:

        if col in df.columns:

            # Convert ke string
            df[col] = df[col].astype(str)

            # Bersihkan format angka
            df[col] = (
                df[col]
                .str.strip()
                .str.replace(',', '.', regex=False)
            )

            # Replace nilai kosong
            df[col] = df[col].replace(
                ['nan', 'None', '', 'NaN'],
                '0'
            )

            # Convert ke numeric
            df[col] = pd.to_numeric(
                df[col],
                errors='coerce'
            ).fillna(0)

    # Pastikan TOTAL float
    if 'TOTAL (m3)' in df.columns:
        df['TOTAL (m3)'] = df['TOTAL (m3)'].astype(float)

    # =========================
    # PRIORITAS SORTING
    # =========================

    if 'RIT' in df.columns:
        df['RIT_PRIORITY'] = df['RIT'].apply(
            lambda x: 0 if x == 2 else 1
        )
    else:
        df['RIT_PRIORITY'] = 0

    sort_cols = ['RIT_PRIORITY']

    for c in ['GRUP', 'ZONA', 'URUT PICKING']:
        if c in df.columns:
            sort_cols.append(c)

    df_sorted = df.sort_values(
        by=sort_cols
    ).reset_index(drop=True)

    # =========================
    # PROSES PENGELOMPOKAN
    # =========================

    packages = []

    current_package = []
    current_vol = 0
    package_id = 1

    for idx, row in df_sorted.iterrows():

        row_total = float(row.get('TOTAL (m3)', 0))

        if len(current_package) == 0:

            current_package.append(row)
            current_vol = row_total

        else:

            first_store = current_package[0]

            # Cek kesamaan rute
            route_match = True

            for c in ['GRUP', 'ZONA', 'RIT']:

                if c in df.columns:

                    if row[c] != first_store[c]:
                        route_match = False

            # Cek kapasitas volume
            vol_ok = (current_vol + row_total) <= max_vol

            # Cek jumlah toko
            stores_ok = len(current_package) < max_st

            # Cek selisih picking
            if 'URUT PICKING' in df.columns:

                all_picking = [
                    float(r['URUT PICKING'])
                    for r in current_package
                ]

                all_picking.append(
                    float(row['URUT PICKING'])
                )

                picking_ok = (
                    max(all_picking) - min(all_picking)
                ) <= max_pick_diff

            else:
                picking_ok = True

            # Jika memenuhi syarat
            if (
                route_match
                and vol_ok
                and stores_ok
                and picking_ok
            ):

                current_package.append(row)
                current_vol += row_total

            else:

                # Simpan paket sebelumnya
                for r in current_package:

                    r_dict = r.to_dict()

                    r_dict['ARMADA_ID'] = f"MOBIL_{package_id:03d}"

                    packages.append(r_dict)

                package_id += 1

                # Paket baru
                current_package = [row]
                current_vol = row_total

    # Simpan paket terakhir
    if current_package:

        for r in current_package:

            r_dict = r.to_dict()

            r_dict['ARMADA_ID'] = f"MOBIL_{package_id:03d}"

            packages.append(r_dict)

    return pd.DataFrame(packages)

# =========================
# MAIN APP
# =========================

if uploaded_file is not None:

    try:

        # Detect delimiter
        bytes_data = uploaded_file.getvalue()

        sample = bytes_data[:2000].decode(
            'utf-8',
            errors='ignore'
        )

        sep = ';' if ';' in sample else ','

        # Read CSV
        df_raw = pd.read_csv(
            io.BytesIO(bytes_data),
            sep=sep
        )

        st.subheader("📊 Data Mentah Terunggah")

        st.dataframe(
            df_raw.head(10),
            use_container_width=True
        )

        # Debug tipe data
        st.subheader("🔍 Tipe Data")

        st.write(df_raw.dtypes)

        # Process
        with st.spinner(
            "Sedang memproses optimasi rute armada..."
        ):

            df_result = process_data(
                df_raw,
                max_volume,
                min_stores,
                max_stores,
                max_picking_diff
            )

        st.success(
            f"⚡ Berhasil mengelompokkan ke dalam "
            f"{df_result['ARMADA_ID'].nunique()} Armada Mobil!"
        )

        # Metrics
        m1, m2, m3 = st.columns(3)

        m1.metric("Total Toko", len(df_result))

        m2.metric(
            "Total Armada",
            df_result['ARMADA_ID'].nunique()
        )

        m3.metric(
            "Rata-rata Toko / Mobil",
            round(
                len(df_result)
                / df_result['ARMADA_ID'].nunique(),
                2
            )
        )

        # Hasil
        st.subheader("📋 Hasil Pengelompokan Paket Mobil")

        display_cols = [
            'ARMADA_ID',
            'KD TOKO',
            'URUT PICKING',
            'RIT',
            'GRUP',
            'ZONA',
            'TOTAL (m3)'
        ]

        available_cols = [
            c for c in display_cols
            if c in df_result.columns
        ]

        st.dataframe(
            df_result[available_cols],
            use_container_width=True
        )

        # Download CSV
        csv_buffer = io.StringIO()

        df_result.to_csv(
            csv_buffer,
            index=False,
            sep=';'
        )

        st.download_button(
            label="📥 Unduh Hasil Pengelompokan (.CSV)",
            data=csv_buffer.getvalue(),
            file_name="hasil_pengelompokan_armada.csv",
            mime="text/csv"
        )

    except Exception as e:

        st.error(
            f"Terjadi kesalahan saat memproses file: {e}"
        )

else:

    st.info(
        "💡 Silakan unggah file CSV data toko "
        "melalui sidebar untuk memulai analisis."
    )

    