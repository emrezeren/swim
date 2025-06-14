import streamlit as st
import pdfplumber
import re
import pandas as pd

# Set page configuration
st.set_page_config(
    page_title="Yüzme Yarış Sonuçları Analizi",
    page_icon="🏊",
    layout="wide"
)


st.title("Yüzme Yarış Sonuçları Analizi 🏊")
st.markdown("---")

uploaded_file = st.file_uploader("PDF dosyasını yükleyin", type="pdf")


def extract_text(pdf_file):
    """PDF dosyasından metin çıkarır"""
    text = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
        return text
    except Exception as e:
        st.error(f"PDF okuma hatası: {str(e)}")
        return ""


def parse_results(text):
    results = []
    current_race = ""
    current_age = ""

    for line in text.splitlines():
        line = line.strip()

        # Yarış başlığı yakala
        if line.startswith("Yarış"):
            current_race = line
            # Yaş bilgisini başlıktan ayıkla (örnek: "10 yaş")
            match_age = re.search(r"(\d{2}) yaş", line)
            current_age = match_age.group(1) if match_age else ""
            continue

        # Sporcu satırı: İsim, YB, Kulüp, Süre, Puan
        match = re.match(
            r"^([A-ZÇĞİÖŞÜ][a-zçğıöşüA-ZÇĞİÖŞÜ\s\-']+)\s+(\d{2})\s+(.*?)\s+((?:\d+:)?\d{2}\.\d{2})\s+(\d+)",
            line
        )

        if match and current_race:
            name = match.group(1).strip()
            yb = int(match.group(2))
            club = match.group(3).strip()
            time = match.group(4).strip()
            score = int(match.group(5))

            results.append({
                "Yarış": current_race,
                "Yaş": current_age,
                "YB": yb,
                "İsim": name,
                "Kulüp": club,
                "Zaman": time,
                "Puan": score
            })

    return pd.DataFrame(results)


if uploaded_file:
    text = extract_text(uploaded_file)
    df = parse_results(text)

    if not df.empty:
        st.success(f"{len(df)} sporcu bulundu, {df['Yarış'].nunique()} yarış algılandı.")
        st.dataframe(df, width=1200, height=400)

        st.subheader("📊 Genel İstatistikler")
        st.write("Toplam yarış sayısı:", df["Yarış"].nunique())
        st.write("Farklı yaş grupları:", sorted(df["Yaş"].dropna().unique()))
        st.write("En yüksek puan:", df["Puan"].max())

        # Süreyi saniyeye çevir
        df["Saniye"] = df["Zaman"].apply(
            lambda z: int(z.split(":")[0]) * 60 + float(z.split(":")[1]) if ":" in z else float(z)
        )

        st.write("En iyi süre:", df["Saniye"].min(), "saniye")
        st.write("Ortalama süre:", round(df["Saniye"].mean(), 2), "saniye")

        # İsteğe bağlı: CSV export
        st.download_button("CSV olarak indir", df.to_csv(index=False), "sonuclar.csv", "text/csv")

    else:
        st.warning("Veri bulunamadı. PDF formatı beklenenden farklı olabilir.")
