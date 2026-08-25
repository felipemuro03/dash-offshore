import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from market_lib import bonds_pdf, fixed_income  # noqa: E402
from market_lib.estilo import aplicar_estilo, mostrar_logo_sidebar  # noqa: E402

st.set_page_config(page_title="Dash Offshore — Fixed Income", layout="wide", page_icon="💵")
aplicar_estilo()
mostrar_logo_sidebar()

st.title("Fixed Income — Acompanhamento de Bonds")
st.caption(
    "Consolida as posições de bonds individuais da Avenue e do BTG US por cliente, e "
    "guarda um histórico de marcação a cada snapshot salvo — pra acompanhar se o deságio "
    "de uma posição está melhorando (ou piorando) ao longo do tempo."
)

CAMINHO_HISTORICO = RAIZ_PROJETO / "data" / "bonds_historico.csv"

st.sidebar.header("1. Subir as planilhas de hoje")
arquivo_avenue = st.sidebar.file_uploader(
    "Posições em Bonds — Avenue (.xlsx)", type=["xlsx"], key="fi_avenue"
)
arquivo_btg = st.sidebar.file_uploader(
    "Unrealized Gain/Loss — BTG US (.xlsx)", type=["xlsx"], key="fi_btg"
)

historico = fixed_income.carregar_historico(CAMINHO_HISTORICO)

if arquivo_avenue is None and arquivo_btg is None:
    if historico.empty:
        st.info("Suba pelo menos uma das planilhas na barra lateral pra começar.")
        st.stop()
    st.info(
        "Nenhuma planilha nova subida agora — mostrando o último snapshot salvo no histórico."
    )
    snapshot_atual = fixed_income.ultimo_snapshot_por_posicao(historico)
else:
    with st.spinner("Lendo planilhas..."):
        avenue_df = fixed_income.carregar_avenue(arquivo_avenue) if arquivo_avenue else None
        btg_df = fixed_income.carregar_btg_us(arquivo_btg) if arquivo_btg else None
        snapshot_atual = fixed_income.montar_snapshot(avenue_df, btg_df)

    st.caption(
        "⚠️ Nesse app publicado (Streamlit Cloud), o botão Salvar abaixo só vale pra esta "
        "sessão — o Streamlit Cloud apaga qualquer arquivo alterado quando o app reinicia. "
        "Pra o histórico ficar valendo de verdade, rode local e suba com `git push`."
    )
    if st.button("💾 Salvar snapshot de hoje no histórico"):
        historico = fixed_income.salvar_snapshot(CAMINHO_HISTORICO, historico, snapshot_atual)
        st.success(f"Snapshot salvo — {len(snapshot_atual)} posições.")

if snapshot_atual.empty:
    st.warning("Nenhuma posição de bond encontrada nas planilhas subidas.")
    st.stop()

st.divider()
st.header("Visão geral")

col_f1, col_f2 = st.columns([2, 1])
with col_f1:
    clientes_selecionados = st.multiselect(
        "Cliente(s)", sorted(snapshot_atual["Cliente"].unique()), key="fi_clientes"
    )
with col_f2:
    custodias_selecionadas = st.multiselect(
        "Custódia",
        sorted(snapshot_atual["Custodia"].unique()),
        default=sorted(snapshot_atual["Custodia"].unique()),
        key="fi_custodias",
    )

tabela = snapshot_atual[snapshot_atual["Custodia"].isin(custodias_selecionadas)]
if clientes_selecionados:
    tabela = tabela[tabela["Cliente"].isin(clientes_selecionados)]
tabela = tabela.sort_values("Variacao (%)")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Posições", len(tabela))
col2.metric("Valor atual total", f"US$ {tabela['Valor Atual (US$)'].sum():,.2f}")
col3.metric("Ágio/Deságio total", f"US$ {tabela['Variacao (US$)'].sum():,.2f}")
col4.metric("Posições com deságio (< 0%)", int((tabela["Variacao (%)"] < 0).sum()))


def _colorir_variacao(val):
    if pd.isna(val):
        return ""
    cor = "#b3261e" if val < 0 else "#1b7a3d"
    return f"color: {cor}; font-weight: 600"


st.dataframe(
    tabela[
        ["Data", "Custodia", "Cliente", "Identificador", "Descricao", "Preco",
         "Valor Atual (US$)", "Valor Compra (US$)", "Variacao (US$)", "Variacao (%)"]
    ]
    .style.map(_colorir_variacao, subset=["Variacao (US$)", "Variacao (%)"])
    .format(
        {
            "Preco": "{:.3f}",
            "Valor Atual (US$)": "US$ {:,.2f}",
            "Valor Compra (US$)": "US$ {:,.2f}",
            "Variacao (US$)": "US$ {:,.2f}",
            "Variacao (%)": "{:.2%}",
        },
        na_rep="-",
    ),
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("Relatório em PDF")
st.caption(
    "Gera um PDF com a tabela acima, respeitando os filtros de cliente/custódia escolhidos "
    "em Visão geral — pra mandar pro cliente (filtre por 1 cliente) ou guardar internamente "
    "(sem filtro, todas as posições)."
)
if tabela.empty:
    st.info("Nenhuma posição para o filtro atual.")
else:
    if len(clientes_selecionados) == 1:
        titulo_pdf = clientes_selecionados[0]
    elif clientes_selecionados:
        titulo_pdf = f"{len(clientes_selecionados)} clientes selecionados"
    else:
        titulo_pdf = "Posição consolidada (todos os clientes)"

    pdf_bytes = bonds_pdf.gerar_pdf_posicao(tabela, titulo_pdf)
    st.download_button(
        "📄 Gerar PDF",
        data=pdf_bytes,
        file_name=f"fixed_income_{dt.date.today().isoformat()}.pdf",
        mime="application/pdf",
        key="fi_download_pdf",
    )

st.divider()
st.header("Evolução de uma posição")

if historico.empty:
    st.info(
        "Ainda não há histórico salvo — salve o snapshot de hoje acima pra começar a "
        "acompanhar a evolução."
    )
else:
    col_cli, col_pos = st.columns(2)
    with col_cli:
        cliente_evolucao = st.selectbox(
            "Cliente", sorted(historico["Cliente"].unique()), key="fi_cliente_evo"
        )
    posicoes_cliente = historico[historico["Cliente"] == cliente_evolucao][
        ["Identificador", "Descricao"]
    ].drop_duplicates()
    opcoes_pos = posicoes_cliente.apply(
        lambda r: f"{r['Descricao']} ({r['Identificador']})", axis=1
    ).tolist()
    mapa_id = dict(zip(opcoes_pos, posicoes_cliente["Identificador"]))
    with col_pos:
        posicao_escolhida = st.selectbox("Posição", opcoes_pos, key="fi_posicao_evo")
    id_escolhido = mapa_id[posicao_escolhida]

    evolucao = fixed_income.evolucao_posicao(historico, cliente_evolucao, id_escolhido)

    if len(evolucao) < 2:
        st.info(
            "Só tem 1 snapshot salvo pra essa posição ainda — suba e salve planilhas em "
            "datas diferentes pra ver a evolução aparecer aqui."
        )

    if evolucao["Preco"].notna().any():
        fig_preco = px.line(evolucao, x="Data", y="Preco", markers=True, title="Marcação (preço)")
        st.plotly_chart(fig_preco, use_container_width=True)
    else:
        st.caption(
            "Essa posição não tem preço de marcação explícito (típico da Avenue) — "
            "acompanhando pela variação % desde a compra abaixo."
        )

    fig_var = px.line(
        evolucao, x="Data", y="Variacao (%)", markers=True, title="Variação (%) desde a compra"
    )
    fig_var.update_layout(yaxis_tickformat=".1%")
    fig_var.add_hline(y=0, line_dash="dash", line_color="gray")
    st.plotly_chart(fig_var, use_container_width=True)

    st.dataframe(
        evolucao[
            ["Data", "Preco", "Valor Atual (US$)", "Variacao (US$)", "Variacao (%)"]
        ].style.format(
            {
                "Preco": "{:.3f}",
                "Valor Atual (US$)": "US$ {:,.2f}",
                "Variacao (US$)": "US$ {:,.2f}",
                "Variacao (%)": "{:.2%}",
            },
            na_rep="-",
        ),
        use_container_width=True,
        hide_index=True,
    )
