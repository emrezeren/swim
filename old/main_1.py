import streamlit as st
import pdfplumber
import re
import pandas as pd
import hashlib
import os

# Set page configuration
st.set_page_config(
    page_title="Yüzme Yarış Sonuçları Analizi",
    page_icon="🏊",
    layout="wide"
)

# Session state initialization
if 'all_data' not in st.session_state:
    st.session_state.all_data = pd.DataFrame()
if 'processed_files' not in st.session_state:
    st.session_state.processed_files = {}
if 'processing' not in st.session_state:
    st.session_state.processing = False

st.title("Yüzme Yarış Sonuçları Analizi")
st.markdown("### Çoklu Şehir Yarışları Analizi")
st.markdown("---")

# Sidebar için kontroller
st.sidebar.header("PDF Dosyaları")
st.sidebar.markdown("Her PDF dosyası bir şehirdeki yarışları temsil eder")
uploaded_files = st.sidebar.file_uploader(
    "PDF dosyalarını yükleyin",
    type="pdf",
    accept_multiple_files=True
)


def get_file_hash(file):
    """Dosya hash'ini hesaplar"""
    file.seek(0)
    content = file.read()
    file.seek(0)
    return hashlib.md5(content).hexdigest()


def get_city_name(filename):
    """Dosya adından şehir ismini çıkarır"""
    # .pdf uzantısını kaldır ve büyük harfe çevir
    city_name = os.path.splitext(filename)[0].upper()
    return city_name


def extract_text(pdf_file):
    """PDF dosyasından metin çıkarır"""
    text = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            total_pages = len(pdf.pages)
            progress_bar = st.progress(0)
            progress_text = st.empty()

            for i, page in enumerate(pdf.pages):
                progress_bar.progress((i + 1) / total_pages)
                progress_text.text(f"Sayfa {i + 1}/{total_pages} işleniyor...")

                t = page.extract_text()
                if t:
                    text += t + "\n"

            progress_bar.empty()
            progress_text.empty()
        return text
    except Exception as e:
        st.error(f"PDF okuma hatası: {str(e)}")
        return ""


def parse_results(text, city_name):
    """Metin verilerini parse eder ve DataFrame'e çevirir"""
    results = []
    current_race = ""
    current_age = ""
    current_gender = ""

    lines = text.splitlines()
    total_lines = len(lines)

    # Progress bar ve text oluştur
    progress_bar = st.progress(0)
    progress_text = st.empty()

    try:
        for i, line in enumerate(lines):
            line = line.strip()

            # Progress göstergesi (her 50 satırda bir güncelle)
            if i % 50 == 0:
                progress = i / total_lines
                progress_bar.progress(progress)
                progress_text.text(f"Satır {i}/{total_lines} işleniyor...")

            # Yarış başlığı yakala (sadece bireysel yarışlar)
            if line.startswith("Yarış") and ("4 x 50m" not in line and "4x50m" not in line):
                current_race = line

                # Cinsiyet bilgisini yakala
                if "Kızlar" in line:
                    current_gender = "Kız"
                elif "Erkekler" in line:
                    current_gender = "Erkek"
                else:
                    current_gender = ""

                # Yaş bilgisini başlıktan ayıkla
                match_age = re.search(r"(\d{1,2}) yaş", line)
                current_age = match_age.group(1) if match_age else ""
                continue

            # Yaş grubu başlıkları
            if line in ["10 yaş", "11 yaş", "12 yaş"] and current_race:
                current_age = line.split()[0]
                continue

            # Sporcu satırı yakala - daha esnek regex
            match = re.match(
                r"^([A-ZÇĞİÖŞÜ][a-zçğıöşüA-ZÇĞİÖŞÜ\s\-']+)\s+(\d{2})\s+(.*?)\s+((?:\d+:)?\d{1,2}\.\d{2})\s+(\d+)",
                line
            )

            if match and current_race and "4 x 50m" not in current_race:
                name = match.group(1).strip()
                yb = int(match.group(2))
                club = match.group(3).strip()
                time = match.group(4).strip()
                score = int(match.group(5))

                # Geçerli zaman kontrolü - sıfır süreleri atla
                seconds = time_to_seconds(time)
                if seconds is None or seconds <= 0:
                    continue

                results.append({
                    "Şehir": city_name,
                    "Yarış": current_race,
                    "Cinsiyet": current_gender,
                    "Yaş": current_age,
                    "YB": yb,
                    "İsim": name,
                    "Kulüp": club,
                    "Zaman": time,
                    "Puan": score
                })

    finally:
        # Progress bar'ı temizle
        progress_bar.progress(1.0)
        progress_text.text("İşlem tamamlandı!")
        progress_bar.empty()
        progress_text.empty()

    return pd.DataFrame(results)


def time_to_seconds(time_str):
    """Zaman stringini saniyeye çevirir"""
    try:
        if ":" in time_str:
            parts = time_str.split(":")
            return int(parts[0]) * 60 + float(parts[1])
        else:
            time_val = float(time_str)
            # Sıfır veya çok küçük değerleri geçersiz say
            return time_val if time_val > 0 else None
    except:
        return None


def calculate_national_rankings(df):
    """Ulusal dereceleri hesaplar"""
    # Her yarış kategorisi için en iyi performansları bul
    rankings = []

    for race in df['Yarış'].unique():
        for gender in df[df['Yarış'] == race]['Cinsiyet'].unique():
            for age in df[(df['Yarış'] == race) & (df['Cinsiyet'] == gender)]['Yaş'].unique():

                # Bu kategorideki tüm sporcular
                category_df = df[
                    (df['Yarış'] == race) &
                    (df['Cinsiyet'] == gender) &
                    (df['Yaş'] == age)
                    ]

                if not category_df.empty:
                    # En yüksek puana göre sırala
                    top_performers = category_df.nlargest(10, 'Puan')

                    for rank, (_, row) in enumerate(top_performers.iterrows(), 1):
                        rankings.append({
                            'Derece': rank,
                            'Yarış': race,
                            'Cinsiyet': gender,
                            'Yaş': age,
                            'İsim': row['İsim'],
                            'Şehir': row['Şehir'],
                            'Kulüp': row['Kulüp'],
                            'Zaman': row['Zaman'],
                            'Puan': row['Puan']
                        })

    return pd.DataFrame(rankings)


def show_basic_stats(df):
    """Temel istatistikleri ve en iyi performansları birleşik olarak gösterir"""
    st.subheader("Genel İstatistikler ve En İyi Performanslar")

    # İlk satır - Genel sayılar
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Toplam Sporcu", len(df))
    with col2:
        st.metric("Şehir Sayısı", df['Şehir'].nunique())
    with col3:
        st.metric("Yarış Sayısı", df["Yarış"].nunique())
    with col4:
        st.metric("Kulüp Sayısı", df['Kulüp'].nunique())

    st.markdown("---")

    # İkinci satır - En iyi performanslar
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        top_score = df.loc[df['Puan'].idxmax()]
        st.metric(
            "En Yüksek Puan",
            f"{top_score['Puan']}",
            f"{top_score['İsim']} ({top_score['Şehir']})"
        )

    with col2:
        best_time = df.loc[df['Saniye'].idxmin()]
        st.metric(
            "En İyi Süre",
            f"{best_time['Zaman']}",
            f"{best_time['İsim']} ({best_time['Şehir']})"
        )

    with col3:
        most_active_city = df['Şehir'].value_counts()
        st.metric(
            "En Aktif Şehir",
            most_active_city.index[0],
            f"{most_active_city.iloc[0]} sporcu"
        )

    with col4:
        avg_score = df['Puan'].mean()
        st.metric(
            "Ortalama Puan",
            f"{avg_score:.1f}",
            f"Min: {df['Puan'].min()} - Max: {df['Puan'].max()}"
        )


def show_club_analysis(df):
    """Kulüp bazında analiz"""
    st.subheader("Kulüp Bazında Performans")

    club_stats = df.groupby('Kulüp').agg({
        'Puan': ['mean', 'max', 'count'],
        'Saniye': 'mean',
        'Şehir': lambda x: ', '.join(sorted(x.unique()))
    }).round(2)

    club_stats.columns = ['Ortalama Puan', 'En Yüksek Puan', 'Sporcu Sayısı', 'Ortalama Süre', 'Katıldığı Şehirler']
    club_stats = club_stats.sort_values('Ortalama Puan', ascending=False)

    # Sadece 2 veya daha fazla sporcusu olan kulüpleri göster
    club_stats_filtered = club_stats[club_stats['Sporcu Sayısı'] >= 2]

    if not club_stats_filtered.empty:
        st.dataframe(club_stats_filtered.head(15), use_container_width=True)
    else:
        st.dataframe(club_stats.head(15), use_container_width=True)


def process_files(uploaded_files):
    """Dosyaları işler ve session state'e kaydeder"""
    if not uploaded_files:
        return pd.DataFrame()

    all_data = []
    new_files_processed = False

    for uploaded_file in uploaded_files:
        file_hash = get_file_hash(uploaded_file)
        city_name = get_city_name(uploaded_file.name)

        # Eğer dosya daha önce işlenmişse cache'den al
        if file_hash in st.session_state.processed_files:
            st.info(f"{city_name} dosyası cache'den yüklendi")
            all_data.append(st.session_state.processed_files[file_hash])
            continue

        # Yeni dosya işle
        st.info(f"⏳ {city_name} dosyası işleniyor...")
        text = extract_text(uploaded_file)

        if text:
            df = parse_results(text, city_name)

            if not df.empty:
                # Süreyi saniyeye çevir
                df["Saniye"] = df["Zaman"].apply(time_to_seconds)

                # Cache'e kaydet
                st.session_state.processed_files[file_hash] = df
                all_data.append(df)
                new_files_processed = True

                st.success(f"✅ {city_name}: {len(df)} sporcu bulundu")
            else:
                st.warning(f"⚠️ {city_name}: Veri bulunamadı")

    # Tüm verileri birleştir
    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)
        st.session_state.all_data = combined_df
        return combined_df

    return pd.DataFrame()


# Ana uygulama mantığı
if uploaded_files:
    df = process_files(uploaded_files)

    if not df.empty:
        # Cache bilgisi
        st.sidebar.success(f"{len(st.session_state.processed_files)} dosya hafızada")
        if st.sidebar.button("Tüm Dosyaları Yeniden İşle"):
            st.session_state.processed_files = {}
            st.session_state.all_data = pd.DataFrame()
            st.rerun()

        # Filtreler
        st.sidebar.header("Filtreler")

        # Filtreleme için kopya oluştur
        filtered_df = df.copy()

        # Şehir filtresi
        city_options = ['Tümü'] + sorted(filtered_df['Şehir'].unique())
        selected_city = st.sidebar.selectbox("Şehir", city_options)
        if selected_city != 'Tümü':
            filtered_df = filtered_df[filtered_df['Şehir'] == selected_city]

        # Cinsiyet filtresi
        if not filtered_df['Cinsiyet'].isna().all():
            gender_options = ['Tümü'] + sorted(filtered_df['Cinsiyet'].dropna().unique())
            selected_gender = st.sidebar.selectbox("Cinsiyet", gender_options)
            if selected_gender != 'Tümü':
                filtered_df = filtered_df[filtered_df['Cinsiyet'] == selected_gender]

        # Yaş filtresi
        if not filtered_df['Yaş'].isna().all():
            age_options = ['Tümü'] + sorted(filtered_df['Yaş'].dropna().unique())
            selected_age = st.sidebar.selectbox("Yaş Grubu", age_options)
            if selected_age != 'Tümü':
                filtered_df = filtered_df[filtered_df['Yaş'] == selected_age]

        # Kulüp filtresi
        club_options = ['Tümü'] + sorted(filtered_df['Kulüp'].unique())
        selected_club = st.sidebar.selectbox("Kulüp", club_options)
        if selected_club != 'Tümü':
            filtered_df = filtered_df[filtered_df['Kulüp'] == selected_club]

        # Tabs için layout
        tab1, tab2, tab3 = st.tabs(["Genel Analiz", "Ulusal Dereceler", "Tüm Sonuçlar"])

        with tab1:
            # Birleşik istatistikler
            show_basic_stats(filtered_df)

            # Kulüp analizi
            st.markdown("---")
            show_club_analysis(filtered_df)

            # Dağılım grafikleri
            st.subheader("Katılımcı Dağılımları")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.write("**Şehir Dağılımı**")
                city_dist = filtered_df['Şehir'].value_counts()
                st.bar_chart(city_dist)

            with col2:
                st.write("**Yaş Grubu Dağılımı**")
                age_dist = filtered_df['Yaş'].value_counts().sort_index()
                st.bar_chart(age_dist)

            with col3:
                st.write("**Cinsiyet Dağılımı**")
                gender_dist = filtered_df['Cinsiyet'].value_counts()
                st.bar_chart(gender_dist)

        with tab2:
            st.subheader("Ülke Dereceleri")

            # Ulusal dereceleri hesapla
            national_rankings = calculate_national_rankings(df)  # Filtrelenmemiş veri kullan

            if not national_rankings.empty:
                # Yarış ve kategori seçimi
                col1, col2, col3 = st.columns(3)

                with col1:
                    race_options = ['Tümü'] + sorted(national_rankings['Yarış'].unique())
                    selected_race = st.selectbox("Yarış", race_options, key="ranking_race")

                with col2:
                    gender_options = ['Tümü'] + sorted(national_rankings['Cinsiyet'].unique())
                    selected_gender_rank = st.selectbox("Cinsiyet", gender_options, key="ranking_gender")

                with col3:
                    age_options = ['Tümü'] + sorted(national_rankings['Yaş'].unique())
                    selected_age_rank = st.selectbox("Yaş", age_options, key="ranking_age")

                # Filtreleme
                ranking_filtered = national_rankings.copy()
                if selected_race != 'Tümü':
                    ranking_filtered = ranking_filtered[ranking_filtered['Yarış'] == selected_race]
                if selected_gender_rank != 'Tümü':
                    ranking_filtered = ranking_filtered[ranking_filtered['Cinsiyet'] == selected_gender_rank]
                if selected_age_rank != 'Tümü':
                    ranking_filtered = ranking_filtered[ranking_filtered['Yaş'] == selected_age_rank]

                # Sonuçları göster
                st.dataframe(ranking_filtered, use_container_width=True, height=400)
            else:
                st.warning("Derece hesaplanamadı.")

        with tab3:
            st.subheader("Tüm Sonuçlar")

            # Sütun sıralaması
            display_columns = ['Şehir', 'Yarış', 'Cinsiyet', 'Yaş', 'İsim', 'YB', 'Kulüp', 'Zaman', 'Puan']
            df_display = filtered_df[display_columns]

            st.dataframe(df_display, use_container_width=True, height=500)

else:
    # Session state temizle eğer dosya yoksa
    st.session_state.all_data = pd.DataFrame()

    st.info("Başlamak için soldaki menüden PDF dosyalarını yükleyin.")
    st.markdown("""
    ### Özellikler
    - **Çoklu Dosya Desteği**: Birden fazla şehirden PDF yükleyebilirsiniz
    - **Otomatik Şehir Tanıma**: Dosya adından şehir ismi algılanır
    - **Ulusal Derece Hesaplama**: Tüm şehirlerden en iyi performanslar
    - **Akıllı Cache**: İşlenen dosyalar hafızada saklanır
    """)