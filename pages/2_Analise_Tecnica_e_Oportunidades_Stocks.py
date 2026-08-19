import sys
from pathlib import Path

import streamlit as st

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_PROJETO))

from market_lib.pagina_ativos import renderizar_pagina
from market_lib.estilo import aplicar_estilo, mostrar_logo_sidebar

st.set_page_config(page_title="Analise Tecnica e Oportunidades Stocks", layout="wide", page_icon="📈")
aplicar_estilo()
mostrar_logo_sidebar()

CAMINHO_UNIVERSO = RAIZ_PROJETO / "data" / "universo_acoes.csv"

renderizar_pagina(
    caminho_universo=CAMINHO_UNIVERSO,
    titulo="Analise Tecnica e Oportunidades Stocks",
    chave_prefixo="stock",
    permitir_nova_categoria=True,
)
