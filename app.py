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
    colonne_tab = [
        "denominazione_strada",
        "STR",
        "centro_costo",
        "tipologia_intervento",
        "rup",
        "denominazione_intervento",
        "stato_procedura",
        "anno_rif",
        "CUP",
    ]
    if "importo_stanziato" in df_filt.columns:
        colonne_tab.append("importo_stanziato")

    col_cfg = {}
    if "importo_stanziato" in df_filt.columns:
        col_cfg["importo_stanziato"] = st.column_config.NumberColumn(
            "Importo stanziato", format="€ %,.2f"
        )

    st.dataframe(
        df_filt[colonne_tab],
        use_container_width=True,
        column_config=col_cfg or None,
    )

    # Grafici generali
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.subheader("Numero interventi per strada")
        st.bar_chart(df_filt.groupby("denominazione_strada").size())
    with col_g2:
        st.subheader("Manutenzioni vs altri")
        n_m = df_filt[df_filt["manut_flag"]].shape[0]
        n_a = df_filt.shape[0] - n_m
        st.bar_chart(
            pd.DataFrame({"Tipo": ["Manutenzioni", "Altri"], "Valore": [n_m, n_a]}).set_index("Tipo")
        )

    # Riepilogo economico
    st.subheader("💶 Riepilogo economico (importo stanziato)")

    if "importo_stanziato" in df_filt.columns:

        df_rip = df_riepilogo(df_filt)

        col_e1, col_e2 = st.columns(2)

        # Somma per strada
        with col_e1:
            st.markdown("**Somma importi per strada**")
            s_str = (
                df_rip.groupby("denominazione_strada")["importo_stanziato"]
                .sum()
                .sort_values(ascending=False)
                .reset_index()
            )
            s_str["Importo (€)"] = s_str["importo_stanziato"].map(fmt_eur)
            st.dataframe(
                s_str[["denominazione_strada", "Importo (€)"]],
                use_container_width=True,
            )

        # Somma per tipologia
        with col_e2:
            st.markdown("**Somma importi per tipologia (dedup STR/determina/importo)**")
            s_tip = (
                df_rip.groupby("tipologia_intervento")["importo_stanziato"]
                .sum()
                .sort_values(ascending=False)
                .reset_index()
            )
            s_tip["Importo (€)"] = s_tip["importo_stanziato"].map(fmt_eur)
            st.dataframe(
                s_tip[["tipologia_intervento", "Importo (€)"]],
                use_container_width=True,
            )

        # Riepilogo: numero di strade coinvolte per tipologia
        st.subheader("🛣️ Strade coinvolte per tipologia")

        strade_per_tip = (
            df_rip.groupby("tipologia_intervento")["denominazione_strada"]
            .nunique()
            .reset_index()
            .rename(columns={"denominazione_strada": "Numero strade"})
            .sort_values("Numero strade", ascending=False)
        )

        st.dataframe(
            strade_per_tip,
            use_container_width=True,
        )

        # Somma per manutenzione (VERO / FALSO)
        st.markdown("**Somma importi per manutenzione (flag da tipologia)**")

        s_man = (
            df_rip.groupby("manut_flag")["importo_stanziato"]
            .sum()
            .reset_index()
        )
        s_man["manutenzione"] = s_man["manut_flag"].map(
            {True: "VERO (manutenzioni)", False: "FALSO (altri interventi)"}
        )
        s_man["Importo (€)"] = s_man["importo_stanziato"].map(fmt_eur)
        st.dataframe(
            s_man[["manutenzione", "Importo (€)"]],
            use_container_width=True,
        )

        totale_generale = s_man["importo_stanziato"].sum()
        st.success(f"**Totale generale stanziato: {fmt_eur(totale_generale)}**")

    else:
        st.info("Colonna 'importo stanziato' non presente.")

    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------------------------------------
# PAGINA STRADA
# -------------------------------------------------------
else:
    strada_sel = pagina
    df_str = df_filt[df_filt["denominazione_strada"] == strada_sel]

    st.markdown('<div class="sulcis-card">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="sulcis-section-title">🛣️ {strada_sel}</div>',
        unsafe_allow_html=True,
    )

    row_str = strade[strade["denominazione_strada"] == strada_sel].head(1)
    if not row_str.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Codice STR:** {row_str.iloc[0].get('STR', '')}")
        with c2:
            st.markdown(f"**Comuni attraversati:** {row_str.iloc[0].get('comuni_attraversati', '')}")
        st.markdown(f"**Localizzazione:** {row_str.iloc[0].get('localizzazione', '')}")

    colonne_base = [
        "tipologia_intervento",
        "rup",
        "denominazione_intervento",
        "stato_procedura",
        "anno_rif",
        "CUP",
    ]
    if "importo_stanziato" in df_str.columns:
        colonne_base.append("importo_stanziato")

    col_cfg_str = {}
    if "importo_stanziato" in df_str.columns:
        col_cfg_str["importo_stanziato"] = st.column_config.NumberColumn(
            "Importo stanziato", format="€ %,.2f"
        )

    st.subheader("📋 Interventi sulla strada")
    st.dataframe(
        df_str[colonne_base],
        use_container_width=True,
        column_config=col_cfg_str or None,
    )

    # Grafici strada
    st.subheader("📊 Grafici strada")
    cg1, cg2 = st.columns(2)
    with cg1:
        st.markdown("**Interventi per tipologia**")
        st.bar_chart(df_str.groupby("tipologia_intervento").size())
    with cg2:
        st.markdown("**Manutenzioni vs altri**")
        n_mi = df_str[df_str["manut_flag"]].shape[0]
        n_ai = df_str.shape[0] - n_mi
        st.bar_chart(
            pd.DataFrame({"Tipo": ["Manutenzioni", "Altri"], "Valore": [n_mi, n_ai]}).set_index("Tipo")
        )

    # Riepilogo per tipologia (strada corrente)
    st.subheader("📌 Riepilogo interventi per tipologia (strada)")

    riepilogo_tip_str = (
        df_str.groupby("tipologia_intervento")
        .size()
        .reset_index(name="Numero interventi")
        .sort_values("Numero interventi", ascending=False)
    )

    st.dataframe(
        riepilogo_tip_str,
        use_container_width=True,
    )

    # ---------------------------------------------------
    # PDF STRADA (OPZIONALE)
    # ---------------------------------------------------
    if REPORTLAB_AVAILABLE:
        def crea_pdf_strada(data: pd.DataFrame, nome: str) -> BytesIO:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            elements = []

            # Logo
            try:
                resp = requests.get(LOGO_URL, timeout=5)
                if resp.status_code == 200:
                    logo = RLImage(BytesIO(resp.content), width=40, height=40)
                    elements.append(logo)
                    elements.append(Spacer(1, 6))
            except Exception:
                pass

            elements.append(Paragraph(f"Report Strada: {nome}", styles["Title"]))
            elements.append(Paragraph("Provincia del Sulcis Iglesiente", styles["Normal"]))
            elements.append(Spacer(1, 12))

            n_tot = len(data)
            n_mn = data[data["manut_flag"]].shape[0]
            elements.append(
                Paragraph(
                    f"Interventi totali: {n_tot} – Manutenzioni: {n_mn} – Altri: {n_tot - n_mn}",
                    styles["Normal"],
                )
            )
            elements.append(Spacer(1, 12))

            # Riepilogo economico semplice per strada
            if "importo_stanziato" in data.columns:
                data_local = data.copy()
                if "determina" in data_local.columns:
                    data_local["determina_norm"] = data_local["determina"].astype(str).str.strip().str.lower()
                data_rip = df_riepilogo(data_local)
                s_tot = data_rip["importo_stanziato"].sum()
                s_mn = data_rip[data_rip["manut_flag"]]["importo_stanziato"].sum()
                s_al = data_rip[~data_rip["manut_flag"]]["importo_stanziato"].sum()
                txt = (
                    f"Importo stanziato totale (dedup STR/determina/importo): {fmt_eur(s_tot)} "
                    f"(Manutenzioni: {fmt_eur(s_mn)} – Altri: {fmt_eur(s_al)})"
                )
                elements.append(Paragraph(txt, styles["Normal"]))
                elements.append(Spacer(1, 12))

            # Tabella dettagli interventi
            hs = styles["Heading5"]
            cs = styles["Normal"]
            cs.fontSize = 8

            table_data = [[
                Paragraph("Tipologia", hs),
                Paragraph("RUP", hs),
                Paragraph("Intervento", hs),
                Paragraph("Stato", hs),
                Paragraph("Anno", hs),
                Paragraph("CUP", hs),
                Paragraph("Importo", hs),
            ]]

            for _, row in data.iterrows():
                if "importo_stanziato" in row and pd.notna(row["importo_stanziato"]):
                    imp_txt = fmt_eur(row["importo_stanziato"])
                else:
                    imp_txt = "-"
                table_data.append([
                    Paragraph(str(row["tipologia_intervento"]), cs),
                    Paragraph(str(row.get("rup", "")), cs),
                    Paragraph(str(row["denominazione_intervento"]), cs),
                    Paragraph(str(row.get("stato_procedura", "")), cs),
                    Paragraph(str(row.get("anno_rif", "")), cs),
                    Paragraph(str(row.get("CUP", "")), cs),
                    Paragraph(imp_txt, cs),
                ])

            t = Table(table_data, repeatRows=1, colWidths=[70, 40, 180, 60, 30, 80, 60])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ALIGN", (6, 1), (6, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ]))
            elements.append(t)

            doc.build(elements)
            buffer.seek(0)
            return buffer

        pdf = crea_pdf_strada(df_str, strada_sel)
        st.download_button(
            label="📄 Scarica report PDF strada",
            data=pdf,
            file_name=f"report_strada_{strada_sel}.pdf",
            mime="application/pdf",
        )
    else:
        st.info("Generazione PDF disabilitata: modulo 'reportlab' non disponibile.")

    st.markdown('</div>', unsafe_allow_html=True)
