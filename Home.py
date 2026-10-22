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
    "Ferramentas para o universo de ativos offshore: posicoes consolidadas, acompanhamento de "
    "bonds e saude dos emissores; novas ferramentas vao entrar aqui conforme forem construidas."
)

st.divider()
st.markdown('<div class="swm-section-label">Posições</div>', unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("#### 🧭 Posições Consolidadas")
    st.write(
        "Visao consolidada de todas as posicoes (Avenue + BTG US) por cliente e por classe "
        "de ativo — Equities, Investment Grade por prazo, High Yield, Emerging Markets, "
        "Money Markets, Inflation, Hybrids, Gold, Crypto e Alternatives."
    )
    st.page_link("pages/3_Posicoes_Consolidadas.py", label="Abrir", icon="➡️")

st.divider()
st.markdown('<div class="swm-section-label">Fixed Income</div>', unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("#### 💵 Fixed Income — Acompanhamento de Bonds")
    st.write(
        "Consolida as posicoes de bonds individuais da Avenue e do BTG US por cliente, "
        "com historico de marcacao pra acompanhar a evolucao do desagio ao longo do tempo."
    )
    st.page_link("pages/4_Fixed_Income.py", label="Abrir", icon="➡️")

with st.container(border=True):
    st.markdown("#### 🎯 Fixed Income — Oportunidades de Alocação")
    st.write(
        "Sobe o bond run da Avenue e/ou do BTG (PDF) e filtra por YTW, rating, prazo, "
        "duration e setor pra achar a melhor oportunidade — com spread vs Treasury e "
        "comparação do mesmo bond entre as duas casas."
    )
    st.page_link("pages/5_Oportunidades_Fixed_Income.py", label="Abrir", icon="➡️")

with st.container(border=True):
    st.markdown("#### 🩺 Emissores (EUA) — números divulgados")
    st.write(
        "Demonstrações dos emissores dos bonds da base exatamente como arquivadas na SEC (10-K/10-Q): "
        "resultado, balanço, dívida e caixa, sem nenhum indicador calculado — cada coluna com o link do "
        "arquivamento (e dos earnings releases) pra conferir direto na fonte."
    )
    st.page_link("pages/6_Credito_Emissores_EUA.py", label="Abrir", icon="➡️")

st.divider()
st.caption(
    "Cada universo de ativos e editavel direto na pagina (botao 'Adicionar ticker ao "
    "universo'), sem precisar editar arquivo. Mais ferramentas offshore chegam aqui em breve."
)
