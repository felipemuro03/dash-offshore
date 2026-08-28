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
    "Holdings — BTG US (.xlsx)", type=["xlsx"], key="fi_btg"
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
with col1, st.container(border=True):
    st.metric("Posições", len(tabela))
with col2, st.container(border=True):
    st.metric("Valor atual total", f"US$ {tabela['Valor Atual (US$)'].sum():,.2f}")
with col3, st.container(border=True):
    st.metric("Ágio/Deságio total", f"US$ {tabela['Variacao (US$)'].sum():,.2f}")
with col4, st.container(border=True):
    st.metric("Posições com deságio (< 0%)", int((tabela["Variacao (%)"] < 0).sum()))

if not tabela.empty:
    st.markdown("")
    col_donut1, col_donut2 = st.columns(2)

    with col_donut1, st.container(border=True):
        st.markdown("###### Maiores ganhadores e perdedores")
        ranking = tabela.sort_values("Variacao (US$)")
        n = min(5, len(ranking))
        indices_ranking = pd.Index(list(ranking.head(n).index) + list(ranking.tail(n).index)).unique()
        grafico_ranking = ranking.loc[indices_ranking].sort_values("Variacao (US$)").copy()
        grafico_ranking["Rótulo"] = (
            grafico_ranking["Cliente"].str.slice(0, 16)
            + " · "
            + grafico_ranking["Descricao"].str.slice(0, 22)
        )
        fig_ranking = px.bar(
            grafico_ranking, x="Variacao (US$)", y="Rótulo", orientation="h",
            color=grafico_ranking["Variacao (US$)"] >= 0,
            color_discrete_map={True: "#1b7a3d", False: "#b3261e"},
        )
        fig_ranking.update_layout(
            showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=280,
            yaxis_title="", xaxis_title="Ágio/Deságio (US$)",
        )
        st.plotly_chart(fig_ranking, use_container_width=True)

    with col_donut2, st.container(border=True):
        st.markdown("###### Ágio x Deságio (valor atual)")
        tabela_situacao = tabela.copy()
        tabela_situacao["Situação"] = tabela_situacao["Variacao (US$)"].apply(
            lambda v: "Ágio" if v >= 0 else "Deságio"
        )
        por_situacao = tabela_situacao.groupby("Situação", as_index=False)["Valor Atual (US$)"].sum()
        fig_situacao = px.pie(
            por_situacao, names="Situação", values="Valor Atual (US$)", hole=0.6,
            color="Situação",
            color_discrete_map={"Ágio": "#1b7a3d", "Deságio": "#b3261e"},
        )
        fig_situacao.update_traces(textinfo="percent+label")
        fig_situacao.update_layout(
            showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=280,
        )
        st.plotly_chart(fig_situacao, use_container_width=True)


def _colorir_variacao(val):
    if pd.isna(val):
        return ""
    cor = "#b3261e" if val < 0 else "#1b7a3d"
    return f"color: {cor}; font-weight: 600"


with st.container(border=True):
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
st.header("Evolução das posições")

if historico.empty:
    st.info(
        "Ainda não há histórico salvo — salve o snapshot de hoje acima pra começar a "
        "acompanhar a evolução."
    )
else:
    cliente_evolucao = st.selectbox(
        "Cliente", sorted(historico["Cliente"].unique()), key="fi_cliente_evo"
    )

    evolucao = fixed_income.evolucao_cliente(historico, cliente_evolucao)

    def _tendencia(diff):
        if pd.isna(diff):
            return "— primeiro registro"
        if diff > 0:
            return "▲ Melhorou"
        if diff < 0:
            return "▼ Piorou"
        return "● Igual"

    def _cor_tendencia(val):
        if val.startswith("▲"):
            return "color: #1b7a3d; font-weight: 600"
        if val.startswith("▼"):
            return "color: #b3261e; font-weight: 600"
        return ""

    evolucao_exibicao = evolucao.copy()
    evolucao_exibicao["Tendência"] = (
        evolucao_exibicao.groupby("Identificador")["Variacao (%)"].diff().apply(_tendencia)
    )

    with st.container(border=True):
        st.caption(
            "Cada posição comparada só com o próprio histórico (não entre bonds "
            "diferentes) — 'primeiro registro' quando só tem 1 snapshot salvo pra aquela "
            "posição ainda."
        )
        st.dataframe(
            evolucao_exibicao[
                ["Data", "Descricao", "Preco", "Valor Atual (US$)", "Variacao (US$)",
                 "Variacao (%)", "Tendência"]
            ]
            .style.map(_cor_tendencia, subset=["Tendência"])
            .format(
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

    pdf_evolucao_bytes = bonds_pdf.gerar_pdf_evolucao(evolucao_exibicao, cliente_evolucao)
    st.download_button(
        "📄 Gerar PDF da evolução",
        data=pdf_evolucao_bytes,
        file_name=f"evolucao_bonds_{cliente_evolucao.replace(' ', '_')}_{dt.date.today().isoformat()}.pdf",
        mime="application/pdf",
        key="fi_download_pdf_evolucao",
    )
