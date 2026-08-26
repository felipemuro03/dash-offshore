"""Paleta e CSS da marca AVIN, compartilhados por todas as paginas."""

from pathlib import Path

import streamlit as st

LOGO_SIDEBAR = Path(__file__).resolve().parents[1] / "assets" / "logo_principal_branco.svg"

NAVY = "#102134"
GOLD = "#BAA377"
GOLD_ESCURO = "#896F3D"
BRANCO = "#FFFFFF"

NAVY_SECUNDARIO = "#1A293F"
BEGE_SECUNDARIO = "#C8BEAA"
CINZA_SECUNDARIO = "#404751"
FUNDO_PAGINA = "#F5F4F1"

PALETA_DONUT = [GOLD, NAVY, BEGE_SECUNDARIO, CINZA_SECUNDARIO, GOLD_ESCURO, NAVY_SECUNDARIO]


def aplicar_estilo():
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Montserrat', Arial, sans-serif;
        }}
        h1, h2, h3 {{
            font-weight: 600 !important;
            color: {NAVY};
        }}
        [data-testid="stMetricLabel"] {{
            font-weight: 600;
            color: {NAVY};
        }}
        [data-testid="stMetricValue"] {{
            color: {NAVY};
        }}
        [data-testid="stSidebar"] {{
            background-color: {NAVY};
        }}
        [data-testid="stSidebar"] * {{
            color: {BRANCO} !important;
        }}
        .stButton > button, .stDownloadButton > button {{
            background-color: {GOLD};
            color: {NAVY};
            border: none;
            font-weight: 600;
        }}
        .stButton > button:hover, .stDownloadButton > button:hover {{
            background-color: {GOLD_ESCURO};
            color: {BRANCO};
        }}
        .stTabs [aria-selected="true"] {{
            color: {GOLD_ESCURO};
            border-bottom-color: {GOLD_ESCURO} !important;
        }}
        .avin-tag {{
            display: inline-block;
            background-color: {BEGE_SECUNDARIO};
            color: {NAVY_SECUNDARIO};
            border-radius: 4px;
            padding: 1px 8px;
            font-size: 0.8em;
            font-weight: 600;
        }}
        .swm-kicker {{
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.8em;
            font-weight: 700;
            color: {GOLD_ESCURO};
            margin-bottom: 0.2em;
        }}
        .swm-section-label {{
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.78em;
            font-weight: 700;
            color: {CINZA_SECUNDARIO};
            margin: 0.4em 0 0.6em 0;
        }}
        [data-testid="stMain"], .main {{
            background-color: {FUNDO_PAGINA};
        }}
        [data-testid="stVerticalBlockBorderWrapper"] {{
            border-radius: 10px !important;
            background-color: {BRANCO};
            border: 1px solid #EDEBE4 !important;
            box-shadow: 0 1px 3px rgba(16, 33, 52, 0.06);
        }}
        [data-testid="stMetricValue"] {{
            font-size: 1.6rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def mostrar_logo_sidebar():
    if LOGO_SIDEBAR.exists():
        st.sidebar.image(str(LOGO_SIDEBAR), width=140)
        st.sidebar.divider()
