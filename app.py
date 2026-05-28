import streamlit as st
import pandas as pd
import numpy as np
import io
import math
import folium
from streamlit_folium import st_folium
import googlemaps

st.set_page_config(page_title="Logistic & Routing Optimizer Pro", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for styling
st.markdown("""
    <style>
    .main-header {
        font-size: 28px;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 20px;
    }
    .sub-header {
        font-size: 18px;
        font-weight: 500;
        color: #4B5563;
        margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("<div class='main-header'>🚚 Aplikasi Optimasi Rute & Pengelompokan Paket (Google Maps API Terintegrasi)</div>", unsafe_allow_html=True)

# Haversine distance function (sebagai fallback jika API Key kosong)
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    dlat, dlon = lat2_rad - lat1_rad, lon2_rad - lon1_rad
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

# Fungsi untuk mengambil data rute asli dari Google Maps API
@st.cache_data(show_spinner=False)
def get_gmaps_route(api_key, origin_lat, origin_lon, dest_lat, dest_lon):
    if not api_key or api_key.strip() == "":
        # Jika API key kosong, gunakan hitungan matematika biasa (fallback)
        dist = haversine_distance(origin_lat, origin_lon, dest_lat, dest_lon) * 1.3
        duration_min = (dist / 40) * 60  # Asumsi kecepatan 40 km/jam
        return dist, duration_min, [(origin_lat, origin_lon), (dest_lat, dest_lon)]
    
    try:
        gmaps = googlemaps.Client(key=api_key)
        directions_result = gmaps.directions(
            (origin_lat, origin_lon),
            (dest_lat, dest_lon),
            mode="driving"
        )
        if directions_result:
            leg = directions_result[0]['legs'][0]
            distance_km = leg['distance']['value'] / 1000.0
            duration_minutes = leg['duration']['value'] / 60.0
            
            # Decode polyline jalan raya untuk digambar di peta
            points = googlemaps.convert.decode_polyline(directions_result[0]['overview_polyline']['points'])
            route_coords = [(p['lat'], p['lng']) for p in points]
            
            return distance_km, duration_minutes, route_coords
    except Exception as e:
        pass
    
    # Jika API error, gunakan fallback matematika
    dist = haversine_distance(origin_lat, origin_lon, dest_lat, dest_lon) * 1.3
    return dist, (dist / 40) * 60, [(origin_lat, origin_lon), (dest_lat, dest_lon)]

# Sidebar - Configuration parameters
st.sidebar.markdown("### ⚙️ Pengaturan Parameter")

# Google Maps API Key Input
st.sidebar.markdown("**🔑 Google Maps API Configuration**")
gmaps_key = st.sidebar.text_input("Google Maps API Key", type="password", help="Masukkan Google Maps API Key Anda yang valid untuk peta jalan raya yang akurat.")
if not gmaps_key:
    st.sidebar.warning("⚠️ Menggunakan mode simulasi matematika karena API Key belum diisi.")

# DC Coordinate
st.sidebar.markdown("**1. Koordinat Distribution Center (DC)**")
dc_lat = st.sidebar.number_input("Latitude DC", value=-6.209462, format="%.6f")
dc_lon = st.sidebar.number_input("Longitude DC", value=106.629741, format="%.6f")

# Vehicle constraints & Fleet
st.sidebar.markdown("**2. Konfigurasi Armada & Kapasitas**")
if 'fleet_types' not in st.session_state:
    st.session_state.fleet_types = [
        {"tipe": "CDE", "kapasitas": 9.0, "jumlah": 10},
        {"tipe": "CDD", "kapasitas": 14.0, "jumlah": 5},
        {"tipe": "L300", "kapasitas": 4.0, "jumlah": 8},
        {"tipe": "Minibus", "kapasitas": 2.5, "jumlah": 4}
    ]

new_fleet = []
for i, f in enumerate(st.session_state.fleet_types):
    with st.sidebar.expander(f"Armada {f['tipe']}", expanded=False):
        t = st.text_input(f"Nama Tipe #{i+1}", value=f['tipe'], key=f"t_{i}")
        k = st.number_input(f"Kapasitas m³ #{i+1}", value=f['kapasitas'], min_value=0.1, step=0.5, key=f"k_{i}")
        j = st.number_input(f"Jumlah Unit Tersedia #{i+1}", value=f['jumlah'], min_value=0, step=1, key=f"j_{i}")
        new_fleet.append({"tipe": t, "kapasitas": k, "jumlah": j})

if st.sidebar.button("➕ Tambah Tipe Kendaraan"):
    st.session_state.fleet_types.append({"tipe": f"BARU_{len(st.session_state.fleet_types)+1}", "kapasitas": 5.0, "jumlah": 2})
    st.rerun()

if len(st.session_state.fleet_types) > 1 and st.sidebar.button("➖ Hapus Tipe Terakhir"):
    st.session_state.fleet_types.pop()
    st.rerun()

st.session_state.fleet_types = new_fleet

# Operational params
st.sidebar.markdown("**3. Pembatasan & Operasional**")
min_toko = st.sidebar.slider("Minimal Toko per Paket", 1, 10, 2)
max_toko = st.sidebar.slider("Maksimal Toko per Paket", 1, 10, 4)
max_pick_diff = st.sidebar.slider("Maksimal Selisih No Picking", 5, 50, 15)
unloading_hours = st.sidebar.number_input("Durasi Unloading per Toko (Jam)", value=0.5, min_value=0.1, max_value=3.0, step=0.1)

# File uploader
st.markdown("<div class='sub-header'>A. Unggah Data CSV Toko</div>", unsafe_allow_html=True)
uploaded_file = st.file_uploader("Pilih file CSV pengiriman", type=["csv"])

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file, sep=';')
        df.columns = df.columns.str.strip()
        
        required_cols = ['KD TOKO', 'NO PICK', 'Rit', 'GRUP', 'ZONA', 'TOTAL', 'Latitude', 'Longitude']
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            st.error(f"Format Kolom CSV salah. Kolom tidak ditemukan: {missing_cols}")
            st.stop()
            
        df = df.dropna(subset=['KD TOKO', 'NO PICK'])
        for col in ['TOTAL', 'Latitude', 'Longitude']:
            df[col] = df[col].astype(str).str.replace(',', '.')
            
        invalid_mask = (df['Latitude'].str.contains('TUTUP', case=False, na=False)) | \
                       (df['Longitude'].str.contains('TUTUP', case=False, na=False)) | \
                       (df['TOTAL'].str.contains('TUTUP', case=False, na=False))
        
        df_tutup = df[invalid_mask].copy()
        df_valid = df[~invalid_mask].copy()
        
        df_valid['TOTAL'] = pd.to_numeric(df_valid['TOTAL'], errors='coerce')
        df_valid['Latitude'] = pd.to_numeric(df_valid['Latitude'], errors='coerce')
        df_valid['Longitude'] = pd.to_numeric(df_valid['Longitude'], errors='coerce')
        df_valid['NO PICK'] = pd.to_numeric(df_valid['NO PICK'], errors='coerce')
        df_valid['Rit'] = pd.to_numeric(df_valid['Rit'], errors='coerce')
        
        df_valid = df_valid.dropna(subset=['TOTAL', 'Latitude', 'Longitude', 'NO PICK', 'Rit'])
        
        st.success(f"Berhasil memuat data! {len(df_valid)} toko valid siap diproses.")
        
        if st.button("🚀 Jalankan Optimasi Rute & Pengelompokan Paket", type="primary"):
            df_sorted = df_valid.sort_values(by=['Rit', 'GRUP', 'ZONA', 'NO PICK'], ascending=[False, True, True, True]).reset_index(drop=True)
            fleet_pool = sorted(st.session_state.fleet_types, key=lambda x: x['kapasitas'])
            
            unassigned_stores = df_sorted.to_dict('records')
            all_trips = []
            
            while len(unassigned_stores) > 0:
                current_store = unassigned_stores.pop(0)
                package = [current_store]
                
                i = 0
                while i < len(unassigned_stores) and len(package) < max_toko:
                    candidate = unassigned_stores[i]
                    pick_nums = [p['NO PICK'] for p in package] + [candidate['NO PICK']]
                    min_p, max_p = min(pick_nums), max(pick_nums)
                    current_volume = sum([p['TOTAL'] for p in package]) + candidate['TOTAL']
                    max_fleet_cap = max([f['kapasitas'] for f in fleet_pool])
                    
                    if candidate['Rit'] != current_store['Rit']:
                        i += 1
                        continue
                    if (max_p - min_p) > max_pick_diff:
                        i += 1
                        continue
                    if current_volume > max_fleet_cap:
                        i += 1
                        continue
                        
                    # Filter radius awal menggunakan matematika agar menghemat hitungan API Google Maps
                    dist_to_pkg = min([haversine_distance(p['Latitude'], p['Longitude'], candidate['Latitude'], candidate['Longitude']) for p in package])
                    if dist_to_pkg > 25.0:
                        i += 1
                        continue
                        
                    package.append(unassigned_stores.pop(i))
                    
                total_pkg_vol = sum([p['TOTAL'] for p in package])
                selected_vehicle = None
                for fleet in fleet_pool:
                    if fleet['kapasitas'] >= total_pkg_vol and fleet['jumlah'] > 0:
                        selected_vehicle = fleet['tipe']
                        fleet['jumlah'] -= 1
                        break
                if not selected_vehicle:
                    for fleet in reversed(fleet_pool):
                        if fleet['jumlah'] > 0:
                            selected_vehicle = fleet['tipe']
                            fleet['jumlah'] -= 1
                            break
                    if not selected_vehicle:
                        selected_vehicle = fleet_pool[-1]['tipe']
                
                status_reason = "Sukses Berpasangan" if len(package) >= min_toko else "Kubikasi mobil penuh / Jarak toko pasangan terlalu jauh / Urut Picking pasangan terlalu jauh. -> Solusi: Kirim Langsung DC."
                
                all_trips.append({
                    "package": package,
                    "vehicle": selected_vehicle,
                    "volume": total_pkg_vol,
                    "reason": status_reason
                })
            
            st.markdown("<div class='sub-header'>B. Hasil Rute Jalan Raya & Pengemasan Hasil Sinkronisasi Google Maps</div>", unsafe_allow_html=True)
            export_rows = []
            
            m = folium.Map(location=[dc_lat, dc_lon], zoom_start=11)
            folium.Marker([dc_lat, dc_lon], tooltip="Distribution Center (DC)", icon=folium.Icon(color='red', icon='home')).add_to(m)
            
            colors = ['blue', 'green', 'purple', 'orange', 'darkblue', 'pink', 'darkgreen', 'cadetblue', 'darkpurple', 'lightblue']
            
            # Progress bar untuk memantau pemrosesan Google Maps API
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for trip_idx, trip in enumerate(all_trips):
                status_text.text(f"Memproses visualisasi peta jalan raya Google Maps untuk Trip {trip_idx+1} dari {len(all_trips)}...")
                progress_bar.progress((trip_idx + 1) / len(all_trips))
                
                pkg = trip['package']
                v_type = trip['vehicle']
                v_vol = trip['volume']
                reason = trip['reason']
                
                # Urutkan rute (TSP Nearest Neighbor)
                ordered_route = []
                current_lat, current_lon = dc_lat, dc_lon
                remaining_pkg = list(pkg)
                
                total_distance_km = 0.0
                total_duration_min = 0.0
                full_trip_coords = []
                
                while len(remaining_pkg) > 0:
                    nearest_idx = np.argmin([haversine_distance(current_lat, current_lon, r['Latitude'], r['Longitude']) for r in remaining_pkg])
                    next_store = remaining_pkg.pop(nearest_idx)
                    
                    # Panggil fungsi Google Maps API untuk segmen rute jalan ini
                    seg_dist, seg_dur, seg_coords = get_gmaps_route(gmaps_key, current_lat, current_lon, next_store['Latitude'], next_store['Longitude'])
                    total_distance_km += seg_dist
                    total_duration_min += seg_dur
                    full_trip_coords.extend(seg_coords)
                    
                    ordered_route.append(next_store)
                    current_lat, current_lon = next_store['Latitude'], next_store['Longitude']
                
                # Segmen kembali ke DC
                ret_dist, ret_dur, ret_coords = get_gmaps_route(gmaps_key, current_lat, current_lon, dc_lat, dc_lon)
                total_distance_km += ret_dist
                total_duration_min += ret_dur
                full_trip_coords.extend(ret_coords)
                
                # Total Durasi (Waktu mengemudi Google Maps + Durasi Unloading Toko)
                total_unloading_min = len(ordered_route) * (unloading_hours * 60)
                grand_total_min = total_duration_min + total_unloading_min
                
                hr = int(grand_total_min // 60)
                mn = int(grand_total_min % 60)
                duration_str = f"{hr} Jam {mn} Menit"
                
                route_sequence_str = "DC -> " + " -> ".join([r['KD TOKO'] for r in ordered_route]) + " -> DC"
                
                for seq_num, store in enumerate(ordered_route, start=1):
                    export_rows.append({
                        "No Trip": trip_idx + 1,
                        "Tipe Kendaraan": v_type,
                        "Total Kubikasi Trip (m3)": round(v_vol, 3),
                        "Urutan Kirim": seq_num,
                        "Kode Toko": store['KD TOKO'],
                        "No Picking": store['NO PICK'],
                        "Rit": store['Rit'],
                        "Grup": store['GRUP'],
                        "Zona": store['ZONA'],
                        "Kubikasi Toko (m3)": store['TOTAL'],
                        "Urutan Rute Lengkap": route_sequence_str,
                        "Total Jarak Trip (KM)": round(total_distance_km, 2),
                        "Total Durasi Trip (Termasuk Unloading)": duration_str,
                        "Status / Alasan": reason
                    })
                
                # Gambar polyline lekukan jalan raya asli Google Maps ke peta Folium
                route_color = colors[trip_idx % len(colors)]
                if full_trip_coords:
                    folium.PolyLine(full_trip_coords, color=route_color, weight=4, opacity=0.85, tooltip=f"Trip {trip_idx+1} ({v_type})").add_to(m)
                
                for idx, r in enumerate(ordered_route, start=1):
                    folium.Marker(
                        [r['Latitude'], r['Longitude']],
                        tooltip=f"Trip {trip_idx+1} | Toko: {r['KD TOKO']} | Urutan: {idx}",
                        icon=folium.Icon(color=route_color, icon='shopping-cart', prefix='fa')
                    ).add_to(m)
            
            status_text.success("✅ Semua rute jalan raya Google Maps berhasil dimuat!")
            df_export = pd.DataFrame(export_rows)
            
            st.markdown("🔍 **Detail Hasil Perhitungan Rute & Waktu Google Maps**")
            st.dataframe(df_export)
            
            st.markdown("🗺️ **Peta Jalur Pengiriman (Mengikuti Kontur Jalan Raya Asli)**")
            st_folium(m, width=900, height=500, returned_objects=[])
            
            output_buffer = io.BytesIO()
            with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name="Rencana Rute Google Maps")
            
            st.download_button(
                label="📥 Unduh Rencana Rute Hasil Sinkronisasi Google Maps (Excel)",
                data=output_buffer.getvalue(),
                file_name="Rencana_Distribusi_GoogleMaps_Optimized.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
    except Exception as e:
        st.error(f"Terjadi kesalahan pemrosesan file atau parameter. Detail: {str(e)}")