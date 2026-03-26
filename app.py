import streamlit as st
import pandas as pd
import re
import os
from io import BytesIO

# Provo a importare reportlab solo se disponibile
try:
    import requests
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        Image as RLImage,
    )
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    REPORTLAB_AVAILABLE = True
except ModuleNotFoundError:
    REPORTLAB_AVAILABLE = False

from pandas.errors import EmptyDataError, ParserError

# -------------------------------------------------------
# CONFIGURAZIONE BASE, COLORI E LOGO
# -------------------------------------------------------
st.set_page_config(layout="wide", page_title="Dashboard Interventi – Strade Provinciali")

LOGO_URL = "https://provincia-sulcis-iglesiente-api.cloud.municipiumapp.it/s3/150x150/s3/20243/sito/stemma.jpg"

PRIMARY_HEX = "#6BE600"
PRIMARY_LIGHT = "#A8FF66"
PRIMARY_EXTRA_LIGHT = "#E8FFE0"

st.markdown(
    f"""
    <style>
    [data-testid="stAppViewContainer"] {{
        background: linear-gradient(135deg, {PRIMARY_EXTRA_LIGHT} 0%, #FFFFFF 40%, {PRIMARY_EXTRA_LIGHT} 100%);
    }}

    .sulcis-main-header {{
        display:flex;
        align-items:center;
        gap:1rem;
        background: linear-gradient(90deg, {PRIMARY_HEX} 0%, {PRIMARY_LIGHT} 50%, {PRIMARY_EXTRA_LIGHT} 100%);
        padding: 0.9rem 1.3rem;
        border-radius: 0.75rem;
        margin-bottom: 1.2rem;
        color: #1E2A10;
        font-weight: 600;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    .sulcis-main-header-text small {{
        display:block;
        font-weight:400;
        opacity:0.9;
        margin-top:0.2rem;
    }}

    .sulcis-card {{
        background: linear-gradient(135deg, #FFFFFF 0%, {PRIMARY_EXTRA_LIGHT} 100%);
        border-radius: 0.75rem;
        padding: 0.9rem 1.1rem;
        margin-bottom: 1rem;
        border: 1px solid rgba(107,230,0,0.25);
    }}

    .sulcis-section-title {{
        font-weight: 600;
        color: #1E2A10;
        margin-bottom: 0.3rem;
    }}

    h1, h2, h3 {{
        margin-top: 0.4rem;
        margin-bottom: 0.4rem;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Header con logo + testo
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.image(LOGO_URL, width=70)
with col_title:
    st.markdown(
        """
        <div class="sulcis-main-header">
            <div class="sulcis-main-header-text">
                Dashboard Interventi Strade Provinciali<br/>
                <small>Provincia del Sulcis Iglesiente – interventi e manutenzioni sulla viabilità provinciale</small>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# -------------------------------------------------------
# PATH BASE E CARTELLA DATA
# -------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

STRADE_FILENAME = "STR02_Strade-Provinciale-ELE_STRD_DWLD-2.csv"
INTERVENTI_FILENAME = "STR02_Strade-Provinciale-STRD_CMPLSS.csv"

# -------------------------------------------------------
# HELPER: DF per riepiloghi economici (strade)
# regola: stessa (STR, determina_norm, importo_stanziato) = 1 volta
# -------------------------------------------------------
def df_riepilogo(df_source: pd.DataFrame) -> pd.DataFrame:
    if not {"STR", "determina_norm", "importo_stanziato"}.issubset(df_source.columns):
        return df_source
    return df_source.drop_duplicates(subset=["STR", "determina_norm", "importo_stanziato"])

# -------------------------------------------------------
# LETTURA CSV DA CARTELLA INTERNA
# -------------------------------------------------------
def load_csv_from_repo(filename: str, nome_log: str = "file") -> pd.DataFrame:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        st.error(f"{nome_log}: file non trovato in 'data/' ({path}).")
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, sep=";", encoding="utf-8", engine="python")
        if df.empty:
            st.error(f"{nome_log}: il file è vuoto (UTF-8).")
        return df
    except (EmptyDataError, ParserError) as e:
        st.error(f"{nome_log}: errore parsing (UTF-8): {e}")
        return pd.DataFrame()
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(path, sep=";", encoding="cp1252", engine="python")
            if df.empty:
                st.error(f"{nome_log}: il file è vuoto (cp1252).")
            return df
        except Exception as e2:
            st.error(f"{nome_log}: fallback cp1252 fallisce: {e2}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"{nome_log}: errore imprevisto: {e}")
        return pd.DataFrame()

# -------------------------------------------------------
# CARICAMENTO DATI STRADE (SENZA UPLOAD)
# -------------------------------------------------------
st.sidebar.subheader("📂 Dati strade da cartella interna")
st.sidebar.write(f"Strade: `data/{STRADE_FILENAME}`")
st.sidebar.write(f"Interventi: `data/{INTERVENTI_FILENAME}`")

strade = load_csv_from_repo(STRADE_FILENAME, "STRADE")
interventi = load_csv_from_repo(INTERVENTI_FILENAME, "INTERVENTI STRADE")

if strade.empty or interventi.empty:
    st.stop()

strade.columns = strade.columns.str.strip()
interventi.columns = interventi.columns.str.strip()

# -------------------------------------------------------
# RINOMINO / NORMALIZZO COLONNE (STRADE)
# -------------------------------------------------------
strade = strade.rename(columns={
    "Denominazione Strada": "denominazione_strada",
    "Localizzazione Strada ¹": "localizzazione",
    "Comune/i attraversati ¹": "comuni_attraversati",
    "Centro Costo": "centro_costo",
})

interventi = interventi.rename(columns={
    "codice": "codice_intervento",
    "Denominazione intervento": "denominazione_intervento",
    "Tipologia di intervento": "tipologia_intervento",
    "RUP": "rup",
    "importo stanziato": "importo_stanziato",
    "Stato della procedura": "stato_procedura",
    "Anno rif": "anno_rif",
})

# Se non esiste una colonna "Determina", per compatibilità creo una fittizia
if "Determina" in interventi.columns:
    interventi = interventi.rename(columns={"Determina": "determina"})
elif "CUP" in interventi.columns:
    interventi["determina"] = interventi["CUP"]
else:
    interventi["determina"] = ""

if "tipologia_intervento" not in interventi.columns:
    interventi["tipologia_intervento"] = "Non specificata"

# -------------------------------------------------------
# CONTROLLI COLONNE
# -------------------------------------------------------
for col in ["STR", "denominazione_strada"]:
    if col not in strade.columns:
        st.error(f"File STRADE: colonna '{col}' mancante. Colonne trovate: {list(strade.columns)}")
        st.stop()

for col in ["STR", "denominazione_intervento", "tipologia_intervento"]:
    if col not in interventi.columns:
        st.error(f"File INTERVENTI STRADE: colonna '{col}' mancante. Colonne trovate: {list(interventi.columns)}")
        st.stop()

# -------------------------------------------------------
# JOIN SU 'STR'
# -------------------------------------------------------
strade["STR"] = strade["STR"].astype(str).str.strip()
interventi["STR"] = interventi["STR"].astype(str).str.strip()

df = interventi.merge(
    strade[["STR", "denominazione_strada", "localizzazione", "comuni_attraversati", "centro_costo"]],
    on="STR",
    how="left",
)

# -------------------------------------------------------
# NORMALIZZAZIONE / FLAG
# -------------------------------------------------------
df["determina_norm"] = df["determina"].astype(str).str.strip().str.lower()
df["tipologia_intervento"] = df["tipologia_intervento"].astype(str).str.strip()
df["manut_flag"] = df["tipologia_intervento"].str.lower().str.contains("manutenzione")

# -------------------------------------------------------
# PULIZIA IMPORTI
# -------------------------------------------------------
def pulisci_importo(val):
    if pd.isna(val):
        return None
    s = str(val).replace("€", "").replace("EUR", "").strip()
    s = re.sub(r"[^\d,.\-]", "", s)
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

if "importo_stanziato" in df.columns:
    df["importo_stanziato"] = df["importo_stanziato"].apply(pulisci_importo)

# -------------------------------------------------------
# NAVIGAZIONE
# -------------------------------------------------------
lista_pagine = ["Home"] + sorted(df["denominazione_strada"].dropna().unique())
st.sidebar.subheader("🧭 Navigazione")
pagina = st.sidebar.radio("Vai a", lista_pagine, key="nav_radio_strade")

# -------------------------------------------------------
# FILTRI GLOBALI
# -------------------------------------------------------
st.sidebar.subheader("🔎 Filtri globali")

filtro_tipologia = st.sidebar.multiselect(
    "Tipologia di intervento",
    sorted(df["tipologia_intervento"].dropna().unique())
)

filtro_manut = st.sidebar.selectbox("Manutenzioni", ["Tutti", "Solo manutenzioni", "Solo altri"])

filtro_comune = st.sidebar.multiselect(
    "Comuni attraversati (contiene)", 
    sorted(
        set(
            c.strip()
            for v in df["comuni_attraversati"].dropna()
            for c in str(v).split(",")
        )
    )
)

df_filt = df.copy()
if filtro_tipologia:
    df_filt = df_filt[df_filt["tipologia_intervento"].isin(filtro_tipologia)]
if filtro_manut == "Solo manutenzioni":
    df_filt = df_filt[df_filt["manut_flag"]]
elif filtro_manut == "Solo altri":
    df_filt = df_filt[~df_filt["manut_flag"]]
if filtro_comune:
    mask = df_filt["comuni_attraversati"].astype(str).apply(
        lambda v: any(c in v for c in filtro_comune)
    )
    df_filt = df_filt[mask]

if df_filt.empty:
    st.warning("Nessun intervento corrisponde ai filtri selezionati.")
    st.stop()

# -------------------------------------------------------
# FORMATTAZIONE IMPORTO
# -------------------------------------------------------
def fmt_eur(x):
    if pd.isna(x):
        return "-"
    return f"€ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# -------------------------------------------------------
# PAGINA HOME
# -------------------------------------------------------
if pagina == "Home":
    st.markdown('<div class="sulcis-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="sulcis-section-title">🏠 Dashboard generale – Strade Provinciali</div>',
        unsafe_allow_html=True,
    )

    # Elenco interventi filtrati
    st.subheader("Elenco interventi (filtrati)")
    colonne_tab 
