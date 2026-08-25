import sys
from pathlib import Path

import streamlit as st

RAIZ_PROJETO = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ_PROJETO))

from market_lib.estilo import aplicar_estilo, mostrar_logo_sidebar

st.set_page_config(page_title="Dash Offshore", layout="wide", page_icon="🌐")
aplicar_estilo()
mostrar_logo_sidebar()

st.markdown('<div class="swm-kicker">Offshore · SWM MFO</div>', unsafe_allow_html=True)
st.title("Dash Offshore")
st.caption(
    "Ferramentas para o universo de ativos offshore — hoje reune a analise quant "
    "de ETFs e acoes; novas ferramentas vao entrar aqui conforme forem construidas."
)

st.divider()

st.markdown('<div class="swm-section-label">Quant</div>', unsafe_allow_html=True)

col_etf, col_stocks = st.columns(2)

with col_etf:
    with st.container(border=True):
        st.markdown("#### 🎯 Analise Tecnica e Oportunidades — ETFs")
        st.write(
            "Universo de ETFs (renda variavel, renda fixa por duration/credito e "
            "alternativos): performance, correlacoes e valor relativo, analise "
            "tecnica e um score consolidado de oportunidades."
        )
        st.page_link(
            "pages/1_Analise_Tecnica_e_Oportunidades_ETFs.py",
            label="Abrir",
            icon="➡️",
        )

with col_stocks:
    with st.container(border=True):
        st.markdown("#### 📈 Analise Tecnica e Oportunidades — Stocks")
        st.write(
            "Mesma leitura da aba de ETFs, aplicada ao universo de acoes individuais: "
            "performance, correlacoes e valor relativo, analise tecnica e score "
            "consolidado de oportunidades."
        )
        st.page_link(
            "pages/2_Analise_Tecnica_e_Oportunidades_Stocks.py",
            label="Abrir",
            icon="➡️",
        )

st.divider()
st.markdown('<div class="swm-section-label">Fixed Income</div>', unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("#### 💵 Fixed Income — Acompanhamento de Bonds")
    st.write(
        "Consolida as posicoes de bonds individuais da Avenue e do BTG US por cliente, "
        "com historico de marcacao pra acompanhar a evolucao do desagio ao longo do tempo."
    )
    st.page_link("pages/3_Fixed_Income.py", label="Abrir", icon="➡️")

st.divider()
st.caption(
    "Cada universo de ativos e editavel direto na pagina (botao 'Adicionar ticker ao "
    "universo'), sem precisar editar arquivo. Mais ferramentas offshore chegam aqui em breve."
)
