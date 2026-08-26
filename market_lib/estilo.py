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
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', Arial, sans-serif;
        }}
        h1, h2, h3 {{
            font-weight: 700 !important;
            color: {NAVY};
        }}
        h1 {{
            border-left: 5px solid {GOLD};
            padding-left: 0.6em;
        }}
        [data-testid="stMetricLabel"] {{
            font-weight: 600;
            color: {CINZA_SECUNDARIO};
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-size: 0.78rem !important;
        }}
        [data-testid="stMetricValue"] {{
            color: {NAVY};
            font-size: 2rem;
            font-weight: 700;
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
            border-radius: 8px;
            font-weight: 600;
        }}
        .stButton > button:hover, .stDownloadButton > button:hover {{
            background-color: {GOLD_ESCURO};
            color: {BRANCO};
        }}
        /* Abas em formato pill (segmented control), estilo "Clientes | Fundos" */
        [data-baseweb="tab-list"] {{
            gap: 4px;
            background-color: #EFEDE7;
            border-radius: 999px;
            padding: 4px;
            display: inline-flex;
        }}
        [data-baseweb="tab"] {{
            border-radius: 999px !important;
            padding: 0.5em 1.3em !important;
            color: {CINZA_SECUNDARIO} !important;
            font-weight: 600;
            border: none !important;
            background-color: transparent;
        }}
        [data-baseweb="tab"][aria-selected="true"] {{
            background-color: {BRANCO} !important;
            color: {NAVY} !important;
            box-shadow: 0 1px 4px rgba(16, 33, 52, 0.18);
        }}
        [data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {{
            display: none !important;
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
        [data-testid="stMain"] .block-container {{
            padding-top: 2.5rem;
            padding-left: 3rem;
            padding-right: 3rem;
            max-width: 1400px;
        }}
        [data-testid="stVerticalBlockBorderWrapper"] {{
            border-radius: 14px !important;
            background-color: {BRANCO};
            border: 1px solid #EDEBE4 !important;
            box-shadow: 0 1px 3px rgba(16, 33, 52, 0.06);
            padding: 0.4em;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def mostrar_logo_sidebar():
    if LOGO_SIDEBAR.exists():
        st.sidebar.image(str(LOGO_SIDEBAR), width=140)
        st.sidebar.divider()
