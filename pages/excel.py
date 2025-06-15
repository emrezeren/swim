import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
from datetime import datetime


class SwimmingParser:
    def __init__(self):
        self.individual_results = []
        self.team_results = []
        self.disqualified = []

    def parse_pdf(self, pdf_file):
        try:
            with pdfplumber.open(pdf_file) as pdf:
                all_text = ""
                for page in pdf.pages:
                    all_text += page.extract_text() + "\n"

            self._process_text(all_text)

            return {
                'individual': pd.DataFrame(self.individual_results),
                'team': pd.DataFrame(self.team_results),
                'disqualified': pd.DataFrame(self.disqualified)
            }

        except Exception as e:
            st.error(f"Hata: {str(e)}")
            return None

    def _process_text(self, text):
        lines = text.split('\n')
        current_race_info = {}
        current_age = None
        position = 1

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Yarış başlığı - Çeşitli formatları destekle
            race_match = None

            # Format 1: "Yarış 9, Kızlar, 200m Sırtüstü, 12 yaş"
            race_match = re.search(r'Yarış\s+(\d+)[,.]?\s*([^,]+)[,.]?\s*([^,]+)[,.]?\s*(\d+)\s*yaş', line)

            if not race_match:
                # Format 2: "Yarış 8 Erkekler, 50m Serbest 10 - 12 yaşları arası"
                race_match = re.search(r'Yarış\s+(\d+)\s+([^,]+)[,.]?\s*([^0-9]+?)\s+(\d+)(?:\s*-\s*\d+)?\s*yaş', line)

            if not race_match:
                # Format 3: "Yarış 13 Kızlar, 4 x 100m Karışık 11 - 12 yaşları arası"
                race_match = re.search(r'Yarış\s+(\d+)\s+([^,]+)[,.]?\s*(.+?)\s+(\d+)(?:\s*-\s*\d+)?\s*yaş', line)

            if race_match:
                race_no = int(race_match.group(1))
                gender_part = race_match.group(2).strip()
                race_type = race_match.group(3).strip()
                age = int(race_match.group(4))

                # Cinsiyet belirleme
                if 'Kızlar' in gender_part or 'Kız' in gender_part:
                    cinsiyet = 'Kız'
                elif 'Erkekler' in gender_part or 'Erkek' in gender_part:
                    cinsiyet = 'Erkek'
                else:
                    cinsiyet = 'Karma'

                current_race_info = {
                    'yarış_no': race_no,
                    'yarış_türü': race_type,
                    'cinsiyet': cinsiyet,
                    'yaş_kategorisi': age
                }

                current_age = current_race_info['yaş_kategorisi']
                position = 1
                continue

            # Yaş kategorisi
            age_match = re.search(r'^(\d+)\s*yaş', line)
            if age_match:
                current_age = int(age_match.group(1))
                position = 1
                continue

            # Diskalifiye
            if 'SW' in line:
                self._parse_disqualified(line, current_race_info, current_age)
                continue

            # Takım yarışı
            if 'x 100m' in current_race_info.get('yarış_türü', ''):
                team_result = self._parse_team_result(line, current_race_info, current_age, position)
                if team_result:
                    self.team_results.append(team_result)
                    position += 1
                continue

            # Bireysel sonuç
            individual_result = self._parse_individual_result(line, current_race_info, current_age, position)
            if individual_result:
                self.individual_results.append(individual_result)
                position += 1

    def _parse_individual_result(self, line, race_info, age, position):
        try:
            # Zaman formatını sondan yakalayarak kulüp adını doğru çıkar
            pattern = r'^([A-ZÇĞIİÖŞÜ][a-zçğıiöşü]+(?:\s+[A-ZÇĞIİÖŞÜ][A-ZÇĞIİÖŞÜa-zçğıiöşü]*)*)\s+(\d{2})\s+(.+?)\s+(\d+:\d+\.\d+|\d+\.\d+)\s+(\d+)$'
            match = re.search(pattern, line)

            if not match:
                return None

            name = match.group(1).strip()
            birth_year = 2000 + int(match.group(2))
            club_part = match.group(3).strip()
            time_str = match.group(4)
            points = int(match.group(5))

            # Kulüp adını temizle - OCR hatalarını düzelt
            club = club_part
            club = club.replace('Kulüb1ü', 'Kulübü')
            club = club.replace('Kulub1ü', 'Kulübü')
            club = club.replace('Kulub1', 'Kulübü')
            club = re.sub(r'\d+$', '', club).strip()

            return {
                'Sıra': position,
                'Yarış_No': race_info.get('yarış_no', ''),
                'Yarış_Türü': race_info.get('yarış_türü', ''),
                'Cinsiyet': race_info.get('cinsiyet', ''),
                'Yaş': age,
                'Sporcu_Adı': name,
                'Doğum_Yılı': birth_year,
                'Kulüp': club,
                'Zaman': time_str,
                'Puan': points
            }

        except Exception:
            return None

    def _parse_team_result(self, line, race_info, age, position):
        try:
            pattern = r'^([A-ZÇĞIİÖŞÜ].+?)\s+(\d+:\d+\.\d+)\s+(\d+)$'
            match = re.search(pattern, line)

            if not match:
                return None

            team_name = match.group(1).strip()
            team_time = match.group(2)
            team_points = int(match.group(3))

            return {
                'Sıra': position,
                'Yarış_No': race_info.get('yarış_no', ''),
                'Yarış_Türü': race_info.get('yarış_türü', ''),
                'Cinsiyet': race_info.get('cinsiyet', ''),
                'Yaş': age,
                'Takım_Adı': team_name,
                'Zaman': team_time,
                'Puan': team_points
            }

        except Exception:
            return None

    def _parse_disqualified(self, line, race_info, age):
        try:
            name_match = re.search(r'^([A-ZÇĞIİÖŞÜ][a-zçğıiöşü]+(?:\s+[A-ZÇĞIİÖŞÜ][a-zçğıiöşü]+)*)', line)

            if name_match:
                name = name_match.group(1)
                reason = line[len(name):].strip()

                self.disqualified.append({
                    'Yarış_No': race_info.get('yarış_no', ''),
                    'Yarış_Türü': race_info.get('yarış_türü', ''),
                    'Cinsiyet': race_info.get('cinsiyet', ''),
                    'Yaş': age,
                    'Sporcu_Adı': name,
                    'Neden': reason
                })

        except Exception:
            pass


def create_excel_file(data_dict):
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if not data_dict['individual'].empty:
            data_dict['individual'].to_excel(writer, sheet_name='Bireysel', index=False)

        if not data_dict['team'].empty:
            data_dict['team'].to_excel(writer, sheet_name='Takım', index=False)

        if not data_dict['disqualified'].empty:
            data_dict['disqualified'].to_excel(writer, sheet_name='Diskalifiye', index=False)

    output.seek(0)
    return output


def main():
    st.set_page_config(page_title="PDF Excel Dönüştürücü", page_icon="🏊‍♂️")

    st.title("PDF → Excel Dönüştürücü")

    # Session state başlatma
    if 'converted_data' not in st.session_state:
        st.session_state.converted_data = None
    if 'file_name' not in st.session_state:
        st.session_state.file_name = None

    uploaded_file = st.file_uploader("PDF dosyası seçin", type=['pdf'])

    # Dosya değiştiğinde session state'i temizle
    if uploaded_file is not None:
        current_file_name = uploaded_file.name
        if st.session_state.file_name != current_file_name:
            st.session_state.converted_data = None
            st.session_state.file_name = current_file_name

    # Dönüştür butonu
    if uploaded_file is not None:
        if st.button("Dönüştür") or st.session_state.converted_data is None:
            with st.spinner("İşleniyor..."):
                parser = SwimmingParser()
                data = parser.parse_pdf(uploaded_file)

                if data is not None:
                    # Session state'e kaydet
                    st.session_state.converted_data = data
                    st.success("✅ Dönüştürme tamamlandı!")

    # Sonuçları göster (session state'den)
    if st.session_state.converted_data is not None:
        data = st.session_state.converted_data

        # Metrikler
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Bireysel", len(data['individual']))
        with col2:
            st.metric("Takım", len(data['team']))
        with col3:
            st.metric("Diskalifiye", len(data['disqualified']))

        # Excel indirme butonu
        excel_file = create_excel_file(data)
        st.download_button(
            label="Excel İndir",
            data=excel_file,
            file_name=f"sonuclar_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # Veri önizleme
        if not data['individual'].empty:
            st.subheader("Veri Önizleme")
            st.dataframe(data['individual'].head(10))

        # Temizle butonu
        if st.button("🗑️ Verileri Temizle"):
            st.session_state.converted_data = None
            st.session_state.file_name = None
            st.rerun()


if __name__ == "__main__":
    main()