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

st.markdown("### Şehir Yarışları Analizi")
st.markdown("---")

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
    """Metin verilerini parse eder ve DataFrame'e çevirir - gelişmiş normalizasyon ile"""
    results = []
    current_race_base = ""
    current_age = ""
    current_gender = ""

    lines = text.splitlines()
    total_lines = len(lines)

    progress_bar = st.progress(0)
    progress_text = st.empty()

    try:
        for i, line in enumerate(lines):
            line = line.strip()

            if i % 50 == 0:
                progress = i / total_lines
                progress_bar.progress(progress)
                progress_text.text(f"Satır {i}/{total_lines} işleniyor...")

            # Gereksiz satırları atla
            if (line.startswith("SW ") or
                    "KATILIM BARAJINI GEÇTİ" in line or
                    "50m:" in line or "100m:" in line or "150m:" in line or "200m:" in line or
                    line.startswith("Puanlar:") or
                    "BARAJLARI" in line or
                    "Sonuçlar" in line or
                    line.startswith("Splash Meet") or
                    "BAŞHAKEM" in line or
                    "ETAP MÜSABAKASI" in line or
                    "YB Zaman Derece" in line):
                continue

            # Yarış başlığı yakala
            if line.startswith("Yarış") and "4 x" not in line and "4x" not in line:
                current_race_base = line

                # Cinsiyet belirle ve normalize et
                if "Kızlar" in line:
                    current_gender = "Kızlar"
                elif "Erkekler" in line:
                    current_gender = "Erkekler"
                elif "Kız" in line:
                    current_gender = "Kızlar"  # Normalize et
                elif "Erkek" in line:
                    current_gender = "Erkekler"  # Normalize et
                else:
                    current_gender = ""

                # Tek yaş formatı kontrolü
                single_age_match = re.search(r"(\d{1,2}) yaş$", line.strip())
                if single_age_match:
                    current_age = single_age_match.group(1)
                    current_race_base = re.sub(r",?\s*\d{1,2}\s*yaş$", "", line).strip()
                else:
                    # Yaş aralığını temizle
                    current_race_base = re.sub(r"\s*\d{1,2}\s*-\s*\d{1,2}\s*yaşları?\s*arası", "", line).strip()
                    current_race_base = re.sub(r"\s*\d{1,2}\s*yaş", "", current_race_base).strip()
                    current_race_base = re.sub(r"\s*yaşları\s*arası", "", current_race_base).strip()
                    current_age = ""
                continue

            # Yaş grubu başlığı
            age_match = re.match(r"^(\d{1,2}) yaş$", line.strip())
            if age_match and current_race_base:
                current_age = age_match.group(1)
                continue

            # Sporcu satırı yakala
            if current_race_base and current_age and current_gender:
                # OCR tolerant parsing
                parsed_athlete = parse_athlete_line_robust(line)

                if parsed_athlete:
                    # Zaman kontrolü
                    seconds = time_to_seconds(parsed_athlete["time"])
                    if seconds is None or seconds <= 0:
                        continue

                    # Yarış başlığını oluştur
                    current_race = f"{current_race_base}, {current_age} yaş" if current_age else current_race_base

                    # Normalize edilmiş kategori oluştur
                    race_category = normalize_race_category_advanced(current_race, current_gender, current_age)

                    results.append({
                        "Şehir": city_name,
                        "Yarış": current_race,  # Orijinal yarış adı
                        "Yarış_Kategori": race_category,  # Normalize edilmiş kategori
                        "Cinsiyet": current_gender,
                        "Yaş": current_age,
                        "YB": parsed_athlete["yb"],
                        "İsim": parsed_athlete["name"],
                        "Kulüp": parsed_athlete["club"],
                        "Zaman": parsed_athlete["time"],
                        "Puan": parsed_athlete["score"]
                    })

    finally:
        progress_bar.progress(1.0)
        progress_text.text("İşlem tamamlandı!")
        progress_bar.empty()
        progress_text.empty()

        # Özet bilgi - normalizasyon sonrası
        if results:
            st.success(f"✅ Toplam {len(results)} sporcu kaydı işlendi")

            # Normalize edilmiş kategoriler özeti
            categories = {}
            for result in results:
                cat = result["Yarış_Kategori"]
                categories[cat] = categories.get(cat, 0) + 1

            # Normalizasyon istatistiği
            original_categories = len(set([result["Yarış"] for result in results]))
            normalized_categories = len(categories)

            if original_categories != normalized_categories:
                st.info(
                    f"🔄 Normalizasyon: {original_categories} farklı format → {normalized_categories} standart kategori")
        else:
            st.warning("⚠️ Hiç sporcu kaydı bulunamadı!")

    return pd.DataFrame(results)


def parse_athlete_line_robust(line):
    """OCR hatalarını tolere eden sporcu satırı parse'ı"""

    # Normal format dene
    match = re.match(
        r"^([A-ZÇĞİÖŞÜ][a-zçğıöşüA-ZÇĞİÖŞÜ\s\-'İıĞğÇçŞşÖöÜü]+?)\s+(\d{2})\s+(.+?)\s+((?:\d+:)?\d{1,2}[.,]\d{2})\s+(\d+)$",
        line
    )

    if match:
        return {
            "name": match.group(1).strip(),
            "yb": int(match.group(2)),
            "club": match.group(3).strip(),
            "time": match.group(4).strip().replace(',', '.'),
            "score": int(match.group(5))
        }

    # OCR hatası için agresif parsing
    time_point_match = re.search(r"(\d{1,2}[:.]\d{2})\s+(\d+)$", line)
    if time_point_match:
        time_raw = time_point_match.group(1).replace(':', '.')
        score_raw = int(time_point_match.group(2))

        remaining = re.sub(r"\s*\d{1,2}[:.]\d{2}\s+\d+$", "", line).strip()

        name_yb_match = re.match(r"^([A-ZÇĞİÖŞÜ][a-zçğıöşüA-ZÇĞİÖŞÜ\s\-'İıĞğÇçŞşÖöÜü]+?)\s+(\d{2})\s+(.+)$", remaining)

        if name_yb_match:
            name_raw = name_yb_match.group(1).strip()
            yb_raw = int(name_yb_match.group(2))
            club_raw = name_yb_match.group(3).strip()

            # OCR hata düzeltmeleri
            club_raw = re.sub(r"1ü:?$", "ü", club_raw)
            club_raw = re.sub(r":+$", "", club_raw)
            club_raw = re.sub(r"\d+$", "", club_raw).strip()

            return {
                "name": name_raw,
                "yb": yb_raw,
                "club": club_raw,
                "time": time_raw,
                "score": score_raw
            }

    return None


def normalize_race_category_advanced(race_title, gender, age):
    """
    Gelişmiş yarış kategorisi normalizasyonu
    Farklı formatları tek standarda çevirir
    """

    # Önce metni temizle
    cleaned_title = race_title.strip()

    # Yarış numarası çıkar
    race_match = re.search(r"Yarış\s+(\d+)", cleaned_title)
    race_num = race_match.group(1) if race_match else "1"

    # Mesafe çıkar
    distance_match = re.search(r"(\d+)m", cleaned_title)
    distance = distance_match.group(0) if distance_match else ""

    # Stil çıkar
    style_map = {
        "serbest": "Serbest",
        "sırtüstü": "Sırtüstü",
        "sırt": "Sırtüstü",
        "kurbağalama": "Kurbağalama",
        "kurbağa": "Kurbağalama",
        "kelebek": "Kelebek",
        "karışık": "Karışık"
    }

    style = ""
    title_lower = cleaned_title.lower()
    for key, value in style_map.items():
        if key in title_lower:
            style = value
            break

    # Cinsiyet standartlaştır
    std_gender = ""
    if gender in ["Kız", "Kızlar"]:
        std_gender = "Kızlar"
    elif gender in ["Erkek", "Erkekler"]:
        std_gender = "Erkekler"
    else:
        std_gender = gender

    # Standart format oluştur: "Yarış X, Cinsiyet, Mesafe Stil, Yaş yaş"
    if all([race_num, std_gender, distance, style, age]):
        return f"Yarış {race_num}, {std_gender}, {distance} {style}, {age} yaş"
    else:
        # Eksik bilgi varsa fallback
        return cleaned_title


def normalize_race_category(race_title, gender, age):
    """Eski fonksiyon - geriye uyumluluk için"""
    return normalize_race_category_advanced(race_title, gender, age)


# Test fonksiyonu
def test_normalization():
    """Normalizasyon testleri"""
    test_cases = [
        ("Yarış 10 Erkekler, 200m Sırtüstü, 11 yaş", "Erkekler", "11"),
        ("Yarış 10, Erkekler, 200m Sırtüstü, 11 yaş", "Erkekler", "11"),
        ("Yarış 1 Kızlar, 100m Serbest, 10 yaş", "Kızlar", "10"),
        ("Yarış 1, Kızlar, 100m Serbest, 10 yaş", "Kızlar", "10"),
        ("Yarış 5, Erkek, 50m Kelebek, 12 yaş", "Erkek", "12"),
    ]

    print("🧪 Yarış Normalizasyon Testi:")
    print("=" * 60)

    results = []
    for race_title, gender, age in test_cases:
        normalized = normalize_race_category_advanced(race_title, gender, age)
        results.append(normalized)
        print(f"Girdi: {race_title}")
        print(f"Çıktı: {normalized}")
        print("-" * 40)

    # Kritik test: Aynı yarışlar birleşiyor mu?
    result1 = results[0]  # "Yarış 10 Erkekler, 200m Sırtüstü, 11 yaş"
    result2 = results[1]  # "Yarış 10, Erkekler, 200m Sırtüstü, 11 yaş"

    print(f"\n✅ Birleştirme Testi:")
    print(f"Format 1: {result1}")
    print(f"Format 2: {result2}")
    print(f"Aynı mı? {'✅ EVET' if result1 == result2 else '❌ HAYIR'}")

    return result1 == result2


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


def show_top_5_by_race(df):
    st.subheader("🏆 Performanslar")

    # Sadece yarış filtresi
    race_options = ['Tümü'] + sorted(df['Yarış'].unique())
    selected_race = st.selectbox("🏊 Yarış Türü Seçin", race_options, key="top5_race")

    # Filtreleme uygula (sadece yarış filtresi)
    if selected_race != 'Tümü':
        filtered_df = df[df['Yarış'] == selected_race]
    else:
        filtered_df = df.copy()

    # Sonuçları göster
    if not filtered_df.empty:
        # En iyi 50 performansı göster (daha fazla veri için)
        top_performers = filtered_df.nsmallest(100, 'Saniye')[
            ['İsim', 'Yarış', 'Şehir', 'Cinsiyet', 'Yaş', 'Zaman', 'Puan', 'Kulüp']]

        # Sıralama numarası ekle
        top_performers = top_performers.reset_index(drop=True)
        top_performers.index = range(1, len(top_performers) + 1)
        top_performers.index.name = 'Sıra'

        st.dataframe(top_performers, use_container_width=True)

        # Özet bilgi
        total_in_category = len(filtered_df)
        shown_results = len(top_performers)

        if selected_race != 'Tümü':
            st.info(
                f"📊 **{selected_race}** kategorisinde "
                f"{shown_results} yarışmacı gösteriliyor.")
        else:
            st.info(
                f"📊 Tüm yarışlarda {total_in_category} sporcu içinden en iyi {shown_results} performans gösteriliyor.")
    else:
        st.warning("⚠️ Seçilen kriterlere uygun veri bulunamadı.")


def show_athlete_analysis(df):
    """Sporcu bazlı analiz - FINA puanına göre sıralama ile"""
    st.subheader("👤 Sporcu Analizi")

    # Sporcu seçimi - filtrelenmiş veriyi kullan
    col1, col2 = st.columns([2, 1])

    with col1:
        # Filtrelenmiş veriden sporcu isimlerini al
        available_athletes = sorted(df['İsim'].unique())

        if len(available_athletes) == 0:
            st.warning("⚠️ Seçilen filtreler ile sporcu bulunamadı.")
            return

        athlete_options = ['Sporcu seçin...'] + available_athletes
        selected_athlete = st.selectbox("🏊 Sporcu Seçin", athlete_options, key="athlete_select")

    with col2:
        if selected_athlete != 'Sporcu seçin...':
            # Seçilen sporcunun filtrelenmiş verideki bilgileri
            athlete_df = df[df['İsim'] == selected_athlete]
            st.metric("📊 Filtrelenmiş Yarış", len(athlete_df))
            if not athlete_df.empty:
                st.metric("🏛️ Kulüp", athlete_df['Kulüp'].iloc[0])

    if selected_athlete != 'Sporcu seçin...':
        athlete_df = df[df['İsim'] == selected_athlete]

        if not athlete_df.empty:
            # Sporcunun tüm yarışları - FINA puanına göre sıralama ile
            st.subheader(f"🏊 {selected_athlete} - Yarış Sonuçları")

            # Filtre uyarısı
            if len(athlete_df) < df[df['İsim'] == selected_athlete].shape[0]:
                st.info(
                    "ℹ️ Sidebar filtrelerine göre sonuçlar gösteriliyor. "
                    "Tüm yarışları görmek için filtreleri temizleyin.")

            # Her yarış için sıralamayı hesapla
            results_with_rank = []

            for _, row in athlete_df.iterrows():
                # Yarış kategorisini belirle
                if 'Yarış_Kategori' in row and pd.notna(row['Yarış_Kategori']) and row['Yarış_Kategori'] != 'N/A':
                    # Normalize edilmiş kategori kullan - filtrelenmiş veri içinde
                    same_category = df[df['Yarış_Kategori'] == row['Yarış_Kategori']].copy()
                    category_name = row['Yarış_Kategori']
                else:
                    # Fallback: Manuel kategori oluştur - filtrelenmiş veri içinde
                    same_category = df[
                        (df['Yarış'] == row['Yarış']) &
                        (df['Cinsiyet'] == row['Cinsiyet']) &
                        (df['Yaş'] == row['Yaş'])
                        ].copy()
                    category_name = f"{row['Yarış']} - {row['Cinsiyet']} {row['Yaş']} yaş"

                if len(same_category) > 0:
                    # DEĞİŞEN KISIM: FINA puanına göre sıralama (yüksek puan = daha iyi)
                    same_category_sorted = same_category.sort_values('Puan', ascending=False)

                    # Sporcunun bu kategorideki FINA puanını al
                    athlete_score = row['Puan']

                    # Sporcunun kaçıncı sırada olduğunu hesapla (puana göre)
                    athlete_rank = 1
                    for _, competitor in same_category_sorted.iterrows():
                        if competitor['Puan'] > athlete_score:
                            athlete_rank += 1
                        elif competitor['Puan'] == athlete_score and competitor['İsim'] != row['İsim']:
                            # Aynı puana sahip farklı sporcular varsa, alfabetik sıraya bak
                            if competitor['İsim'] < row['İsim']:
                                athlete_rank += 1

                    total_athletes = len(same_category)

                    # Debug için puan karşılaştırması
                    better_scores = same_category[same_category['Puan'] > athlete_score]
                    calculated_rank = len(better_scores) + 1

                    results_with_rank.append({
                        'Yarış': row['Yarış'],
                        'Şehir': row['Şehir'],
                        'Kategori': f"{row['Cinsiyet']} {row['Yaş']} yaş",
                        'Zaman': row['Zaman'],
                        'Puan_Debug': f"{athlete_score} FINA puan",
                        'Puan': row['Puan'],
                        'Sıralama': f"{calculated_rank}/{total_athletes}",
                        'Derece': calculated_rank,
                        'Yarış_Kategori': category_name,
                        'Daha_Yüksek_Puan_Var': len(better_scores)
                    })

            if results_with_rank:
                # DataFrame oluştur ve en iyi dereceye göre sırala
                results_df = pd.DataFrame(results_with_rank)
                results_df = results_df.sort_values('Derece', ascending=True)

                # Sütun sıralaması - temiz görünüm
                display_results = results_df[['Yarış', 'Şehir', 'Kategori', 'Zaman', 'Puan', 'Sıralama']]
                display_results.index = range(1, len(display_results) + 1)

                st.dataframe(display_results, use_container_width=True)

                # Gelişmiş debug bilgisi
                if st.checkbox("🔍 Debug: Detaylı Sıralama Bilgisi"):
                    debug_df = results_df[
                        ['Yarış', 'Zaman', 'Puan_Debug', 'Daha_Yüksek_Puan_Var', 'Derece', 'Sıralama', 'Yarış_Kategori']]
                    st.dataframe(debug_df, use_container_width=True)

                    # En iyi ve en kötü performans detayı
                    st.write("**🎯 Detaylı Analiz:**")
                    best_perf = results_df.iloc[0]
                    worst_perf = results_df.iloc[-1]

                    col1, col2 = st.columns(2)
                    with col1:
                        st.success(
                            f"**En İyi:** {best_perf['Yarış']} - {best_perf['Derece']}. sıra ({best_perf['Puan']} FINA puan)")
                    with col2:
                        st.info(
                            f"**En Zayıf:** {worst_perf['Yarış']} - {worst_perf['Derece']}. sıra ({worst_perf['Puan']} FINA puan)")

                # Performans özeti
                st.subheader("📊 Performans Özeti")
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    first_places = len([r for r in results_with_rank if r['Derece'] == 1])
                    st.metric("🥇 1. Sıra", first_places)

                with col2:
                    podium_places = len([r for r in results_with_rank if r['Derece'] <= 3])
                    st.metric("🏆 Podyum (Top 3)", podium_places)

                with col3:
                    avg_rank = sum([r['Derece'] for r in results_with_rank]) / len(results_with_rank)
                    st.metric("📈 Ortalama Sıra", f"{avg_rank:.1f}")

                with col4:
                    avg_score = sum([r['Puan'] for r in results_with_rank]) / len(results_with_rank)
                    st.metric("⭐ Ortalama FINA", f"{avg_score:.0f}")

                # Performans trendi (opsiyonel)
                if len(results_with_rank) > 1:
                    st.subheader("📈 Performans Dağılımı")

                    # Derece dağılımı
                    rank_counts = {}
                    for r in results_with_rank:
                        rank = r['Derece']
                        if rank <= 3:
                            rank_counts['🥇 1-3. sıra'] = rank_counts.get('🥇 1-3. sıra', 0) + 1
                        elif rank <= 5:
                            rank_counts['🥈 4-5. sıra'] = rank_counts.get('🥈 4-5. sıra', 0) + 1
                        elif rank <= 10:
                            rank_counts['🥉 6-10. sıra'] = rank_counts.get('🥉 6-10. sıra', 0) + 1
                        else:
                            rank_counts['📊 10+. sıra'] = rank_counts.get('📊 10+. sıra', 0) + 1

                    if rank_counts:
                        st.bar_chart(rank_counts)

            else:
                st.warning("⚠️ Bu sporcu için sıralama hesaplanamadı.")
        else:
            st.warning("⚠️ Seçilen sporcu için veri bulunamadı.")

def show_club_analysis(df):
    """Kulüp bazında analiz"""
    st.subheader("Kulüp Bazında Performans")

    club_stats = df.groupby('Kulüp').agg({
        'Puan': ['mean', 'max', 'count'],
        'Saniye': 'mean',
        'Şehir': lambda x: ', '.join(sorted(x.unique()))
    }).round(0)

    club_stats.columns = ['Ortalama Puan', 'En Yüksek Puan', 'Sporcu Sayısı', 'Ortalama Süre', 'Katıldığı Şehirler']
    club_stats = club_stats.sort_values('Ortalama Puan', ascending=False)

    # Sadece 2 veya daha fazla sporcusu olan kulüpleri göster
    club_stats_filtered = club_stats[club_stats['Sporcu Sayısı'] >= 2]

    if not club_stats_filtered.empty:
        st.dataframe(club_stats_filtered.head(15), use_container_width=True)
        st.caption("Not: Sadece 2 veya daha fazla sporcusu olan kulüpler gösteriliyor.")
    else:
        st.dataframe(club_stats.head(15), use_container_width=True)
        st.caption("Tüm kulüpler gösteriliyor.")


def process_files(uploaded_files):
    """Dosyaları işler ve session state'e kaydeder"""
    if not uploaded_files:
        return pd.DataFrame()

    all_data = []

    for uploaded_file in uploaded_files:
        file_hash = get_file_hash(uploaded_file)
        city_name = get_city_name(uploaded_file.name)

        # Eğer dosya daha önce işlenmişse cache'den al
        if file_hash in st.session_state.processed_files:
            all_data.append(st.session_state.processed_files[file_hash])
            continue

        # Yeni dosya işle
        text = extract_text(uploaded_file)

        if text:
            df = parse_results(text, city_name)

            if not df.empty:
                # Süreyi saniyeye çevir ve geçersiz kayıtları filtrele
                df["Saniye"] = df["Zaman"].apply(time_to_seconds)

                # Sıfır veya None süre değerlerini kaldır
                df = df.dropna(subset=['Saniye'])
                df = df[df['Saniye'] > 0]

                if df.empty:
                    continue

                # Cache'e kaydet
                st.session_state.processed_files[file_hash] = df
                all_data.append(df)

    # Tüm verileri birleştir
    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)

        # Yarış_Kategori sütunu yoksa oluştur (eski cache'ler için)
        if 'Yarış_Kategori' not in combined_df.columns:
            combined_df['Yarış_Kategori'] = combined_df.apply(
                lambda row: normalize_race_category_advanced(row['Yarış'], row['Cinsiyet'], row['Yaş']),
                axis=1
            )

        st.session_state.all_data = combined_df
        return combined_df

    return pd.DataFrame()


# Ana uygulama mantığı
if uploaded_files:
    df = process_files(uploaded_files)

    if not df.empty:
        # Başarı mesajı ve temel istatistikler
        col1, col2, col3 = st.columns(3)
        with col1:
            st.success(f"✅ {len(df)} sporcu bulundu")
        with col2:
            st.info(
                f"🏊 {df['Yarış_Kategori'].nunique() if 'Yarış_Kategori' in df.columns else df['Yarış'].nunique()} farklı yarış")
        with col3:
            st.info(f"🏆 {df['Şehir'].nunique()} şehir")

        # Cache bilgisi
        st.sidebar.success(f"📁 {len(st.session_state.processed_files)} dosya hafızada")
        if st.sidebar.button("🔄 Yeniden İşle"):
            st.session_state.processed_files = {}
            st.session_state.all_data = pd.DataFrame()
            st.rerun()

        # Filtreler
        st.sidebar.header("🔍 Filtreler")

        # Filtreleme için kopya oluştur
        filtered_df = df.copy()

        # Şehir filtresi
        city_options = ['Tümü'] + sorted(filtered_df['Şehir'].unique())
        selected_city = st.sidebar.selectbox("🏙️ Şehir", city_options)
        if selected_city != 'Tümü':
            filtered_df = filtered_df[filtered_df['Şehir'] == selected_city]

        # Cinsiyet filtresi
        if not filtered_df['Cinsiyet'].isna().all():
            gender_options = ['Tümü'] + sorted(filtered_df['Cinsiyet'].dropna().unique())
            selected_gender = st.sidebar.selectbox("👫 Cinsiyet", gender_options)
            if selected_gender != 'Tümü':
                filtered_df = filtered_df[filtered_df['Cinsiyet'] == selected_gender]

        # Yaş filtresi
        if not filtered_df['Yaş'].isna().all():
            age_options = ['Tümü'] + sorted(filtered_df['Yaş'].dropna().unique())
            selected_age = st.sidebar.selectbox("🎂 Yaş Grubu", age_options)
            if selected_age != 'Tümü':
                filtered_df = filtered_df[filtered_df['Yaş'] == selected_age]

        # Kulüp filtresi
        club_options = ['Tümü'] + sorted(filtered_df['Kulüp'].unique())
        selected_club = st.sidebar.selectbox("🏊‍♀️ Kulüp", club_options)
        if selected_club != 'Tümü':
            filtered_df = filtered_df[filtered_df['Kulüp'] == selected_club]

        # Tabs için layout
        tab1, tab2, tab3, tab4 = st.tabs(
            ["📊 Tüm Sonuçlar", "🏆 Performanslar", "👤 Sporcu Analizi", "🏛️ Kulüp Analizi"])

        with tab1:
            st.subheader("📊 Tüm Sonuçlar")

            # Sütun sıralaması - Yarış_Kategori sütununu gizle
            display_columns = ['Şehir', 'Yarış', 'Cinsiyet', 'Yaş', 'İsim', 'YB', 'Kulüp', 'Zaman', 'Puan']
            df_display = filtered_df[display_columns]

            st.dataframe(df_display, use_container_width=True, height=500)

            # İstatistik bilgisi
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("👥 Toplam Sporcu", len(filtered_df))
            with col2:
                st.metric("🏊 Farklı Yarış",
                          filtered_df['Yarış_Kategori'].nunique() if 'Yarış_Kategori' in filtered_df.columns else
                          filtered_df['Yarış'].nunique())
            with col3:
                st.metric("📊 Ortalama Puan", f"{filtered_df['Puan'].mean():.1f}")

        with tab2:
            # En iyi performanslar için güncelleme
            show_top_5_by_race(filtered_df)

            # Dağılım grafikleri
            st.subheader("📈 Katılımcı Dağılımları")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.write("**🏙️ Şehir Dağılımı**")
                city_dist = filtered_df['Şehir'].value_counts()
                st.bar_chart(city_dist)

            with col2:
                st.write("**🎂 Yaş Grubu Dağılımı**")
                age_dist = filtered_df['Yaş'].value_counts().sort_index()
                st.bar_chart(age_dist)

            with col3:
                st.write("**👫 Cinsiyet Dağılımı**")
                gender_dist = filtered_df['Cinsiyet'].value_counts()
                st.bar_chart(gender_dist)

        with tab3:
            # Sporcu analizi - filtrelenmiş veri kullan
            show_athlete_analysis(filtered_df)

        with tab4:
            # Kulüp analizi
            show_club_analysis(filtered_df)

    elif st.session_state.processing:
        st.info("⏳ Dosya işleniyor...")
    else:
        st.warning("⚠️ Veri bulunamadı.")

else:
    # Session state temizle eğer dosya yoksa
    st.session_state.all_data = pd.DataFrame()