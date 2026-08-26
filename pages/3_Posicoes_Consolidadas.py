import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from market_lib import classificacao, posicoes_consolidadas  # noqa: E402
from market_lib.estilo import PALETA_DONUT, aplicar_estilo, mostrar_logo_sidebar  # noqa: E402

st.set_page_config(page_title="Dash Offshore — Posições Consolidadas", layout="wide", page_icon="🧭")
aplicar_estilo()
mostrar_logo_sidebar()

st.title("Posições Consolidadas")
st.caption(
    "Visão consolidada de todas as posições (Avenue + BTG US), por cliente e por classe de "
    "ativo — Equities (US/Global/EM), Investment Grade por prazo, High Yield, Emerging "
    "Markets, Money Markets, Inflation, Hybrids, Gold, Crypto e Alternatives."
)

CAMINHO_CLASSIFICACAO = RAIZ_PROJETO / "data" / "classificacao_ativos.csv"

st.sidebar.header("1. Subir as planilhas")
arquivo_avenue = st.sidebar.file_uploader(
    "Data — Avenue, em US$ (.xlsx)", type=["xlsx"], key="pc_avenue"
)
arquivo_btg = st.sidebar.file_uploader(
    "Holdings — BTG US (.xlsx)", type=["xlsx"], key="pc_btg"
)

if arquivo_avenue is None and arquivo_btg is None:
    st.info("Suba pelo menos uma das planilhas na barra lateral pra começar.")
    st.stop()

with st.spinner("Lendo e classificando as posições..."):
    avenue_df = posicoes_consolidadas.carregar_avenue_data(arquivo_avenue) if arquivo_avenue else None
    btg_df = posicoes_consolidadas.carregar_btg_holdings(arquivo_btg) if arquivo_btg else None
    manual_df = classificacao.carregar_classificacao_manual(CAMINHO_CLASSIFICACAO)
    posicoes = posicoes_consolidadas.montar_posicoes(avenue_df, btg_df, manual_df)

if posicoes.empty:
    st.warning("Nenhuma posição encontrada nas planilhas subidas.")
    st.stop()

st.divider()


def _grafico_composicao_classe(df, titulo, altura=420):
    por_classe = df.groupby("Classe", dropna=False)["Valor Atual (US$)"].sum().reset_index()
    por_classe["Classe"] = por_classe["Classe"].fillna("Não classificado")
    por_classe = por_classe.sort_values("Valor Atual (US$)", ascending=True)
    fig = px.bar(
        por_classe, x="Valor Atual (US$)", y="Classe", orientation="h",
        color_discrete_sequence=[PALETA_DONUT[0]],
    )
    fig.update_layout(
        showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=altura,
        yaxis_title="", xaxis_title="Valor (US$)",
    )
    st.markdown(f"###### {titulo}")
    st.plotly_chart(fig, use_container_width=True)


custodias_sel = st.multiselect(
    "Custódia", sorted(posicoes["Custodia"].unique()),
    default=sorted(posicoes["Custodia"].unique()), key="pc_custodias",
)
posicoes_custodia = posicoes[posicoes["Custodia"].isin(custodias_sel)]

tab_consolidado, tab_liquidez, tab_detalhe = st.tabs(
    ["📊 Visão Consolidada", "💧 Liquidez", "🔎 Detalhe por Cliente"]
)

with tab_consolidado:
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        clientes_sel = st.multiselect(
            "Cliente(s)", sorted(posicoes_custodia["Cliente"].dropna().unique()), key="pc_clientes"
        )
    with col_f2:
        classes_sel = st.multiselect("Classe", classificacao.CLASSES, key="pc_classes")

    tabela = posicoes_custodia.copy()
    if clientes_sel:
        tabela = tabela[tabela["Cliente"].isin(clientes_sel)]
    if classes_sel:
        tabela = tabela[tabela["Classe"].isin(classes_sel)]

    col1, col2, col3, col4 = st.columns(4)
    with col1, st.container(border=True):
        st.metric("Posições", len(tabela))
    with col2, st.container(border=True):
        st.metric("Valor total", f"US$ {tabela['Valor Atual (US$)'].sum():,.2f}")
    with col3, st.container(border=True):
        st.metric("Clientes", tabela["Cliente"].nunique())
    with col4, st.container(border=True):
        n_revisar = int((tabela["Confiança"] == "baixa").sum())
        st.metric(
            "Posições p/ revisar", n_revisar,
            help="Classificação automática com confiança baixa — vale conferir na tabela de classificação manual mais abaixo.",
        )

    if not tabela.empty:
        st.markdown("")
        with st.container(border=True):
            if clientes_sel and len(clientes_sel) == 1:
                titulo_composicao = f"Composição por classe — {clientes_sel[0]}"
            elif clientes_sel:
                titulo_composicao = f"Composição por classe — {len(clientes_sel)} clientes selecionados"
            else:
                titulo_composicao = "Composição por classe — consolidado (todos os clientes)"
            _grafico_composicao_classe(tabela, titulo_composicao)

    st.markdown("")
    st.markdown("###### Por cliente")
    por_cliente = (
        tabela.groupby("Cliente", as_index=False)["Valor Atual (US$)"].sum()
        .sort_values("Valor Atual (US$)", ascending=False)
    )
    with st.container(border=True):
        st.dataframe(
            por_cliente.style.format({"Valor Atual (US$)": "US$ {:,.2f}"}),
            use_container_width=True,
            hide_index=True,
            height=280,
        )

with tab_liquidez:
    st.caption(
        "Ideal: até 10% do patrimônio total em liquidez. Quem estiver acima aparece aqui, "
        "com quanto precisa reduzir pra voltar no limite. Considera o patrimônio total do "
        "cliente (todas as classes) na custódia selecionada acima."
    )

    liquidez_df = posicoes_consolidadas.calcular_liquidez_por_cliente(posicoes_custodia)
    acima_limite = liquidez_df[liquidez_df["% Liquidez"] > posicoes_consolidadas.LIMITE_LIQUIDEZ_PADRAO]

    with st.container(border=True):
        if acima_limite.empty:
            st.success("Nenhum cliente acima do limite de 10% de liquidez.")
        else:
            st.dataframe(
                acima_limite.style.format({
                    "Patrimônio Total": "US$ {:,.2f}",
                    "Money Markets": "US$ {:,.2f}",
                    "% Liquidez": "{:.1%}",
                    "Reduzir (US$)": "US$ {:,.2f}",
                }),
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("")
    st.markdown("###### Ver o que um cliente tem em Money Markets")
    clientes_com_liquidez = sorted(liquidez_df[liquidez_df["Money Markets"] > 0]["Cliente"].unique())
    if clientes_com_liquidez:
        cliente_liquidez_sel = st.selectbox("Cliente", clientes_com_liquidez, key="pc_cliente_liquidez")
        posicoes_mm_cliente = posicoes_custodia[
            (posicoes_custodia["Cliente"] == cliente_liquidez_sel)
            & (posicoes_custodia["Classe"] == "Money Markets")
        ]
        linha_resumo = liquidez_df[liquidez_df["Cliente"] == cliente_liquidez_sel].iloc[0]

        col1, col2, col3 = st.columns(3)
        with col1, st.container(border=True):
            st.metric("Patrimônio total", f"US$ {linha_resumo['Patrimônio Total']:,.2f}")
        with col2, st.container(border=True):
            st.metric("Em Money Markets", f"US$ {linha_resumo['Money Markets']:,.2f}")
        with col3, st.container(border=True):
            st.metric("% Liquidez", f"{linha_resumo['% Liquidez']:.1%}")

        with st.container(border=True):
            st.dataframe(
                posicoes_mm_cliente[["Custodia", "Ticker", "Descricao", "Valor Atual (US$)"]]
                .sort_values("Valor Atual (US$)", ascending=False)
                .style.format({"Valor Atual (US$)": "US$ {:,.2f}"}),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.caption("Nenhum cliente com posição em Money Markets na custódia selecionada.")

with tab_detalhe:
    cliente_detalhe = st.selectbox(
        "Cliente", sorted(posicoes_custodia["Cliente"].dropna().unique()), key="pc_cliente_detalhe"
    )
    posicoes_cliente = posicoes_custodia[posicoes_custodia["Cliente"] == cliente_detalhe]

    col1, col2 = st.columns(2)
    with col1, st.container(border=True):
        st.metric("Patrimônio total", f"US$ {posicoes_cliente['Valor Atual (US$)'].sum():,.2f}")
    with col2, st.container(border=True):
        st.metric("Posições", len(posicoes_cliente))

    st.markdown("")
    with st.container(border=True):
        _grafico_composicao_classe(posicoes_cliente, f"Asset Allocation — {cliente_detalhe}", altura=380)

    st.markdown("")
    st.markdown("###### Posições detalhadas")
    with st.container(border=True):
        st.dataframe(
            posicoes_cliente[["Custodia", "Ticker", "Descricao", "Categoria", "Classe", "Valor Atual (US$)"]]
            .sort_values("Valor Atual (US$)", ascending=False)
            .style.format({"Valor Atual (US$)": "US$ {:,.2f}"}, na_rep="-"),
            use_container_width=True,
            hide_index=True,
        )

st.divider()
st.subheader("Classificação manual")
st.caption(
    "Uma linha por ativo distinto (não por posição/cliente) — corrija a coluna Classe pra "
    "quem estiver errado e clique em Salvar. Isso vale pra tudo (mesmo o que já veio "
    "classificado automaticamente) — depois de salvar, essa classificação passa a valer "
    "sempre, independente da regra automática."
)
st.caption(
    "⚠️ Nesse app publicado (Streamlit Cloud), o botão Salvar abaixo só vale pra esta "
    "sessão — o Streamlit Cloud apaga qualquer arquivo alterado quando o app reinicia. "
    "Pra ficar valendo de verdade, rode local e suba com `git push`."
)

ativos_distintos = (
    posicoes[["Ticker", "Descricao", "Categoria", "Classe", "Confiança"]]
    .drop_duplicates(subset=["Descricao"])
    .sort_values(["Confiança", "Descricao"])
    .reset_index(drop=True)
)

editor_classificacao = st.data_editor(
    ativos_distintos,
    column_config={
        "Classe": st.column_config.SelectboxColumn("Classe", options=classificacao.CLASSES, required=False),
        "Confiança": st.column_config.TextColumn("Confiança (antes de editar)", disabled=True),
        "Categoria": st.column_config.TextColumn("Categoria", disabled=True),
        "Ticker": st.column_config.TextColumn("Ticker", disabled=True),
        "Descricao": st.column_config.TextColumn("Ativo", disabled=True),
    },
    hide_index=True,
    use_container_width=True,
    height=400,
    key="pc_editor_classificacao",
)

if st.button("💾 Salvar classificação"):
    novo_manual = pd.DataFrame({
        "Chave": editor_classificacao["Descricao"].apply(classificacao.normalizar_chave),
        "Classe": editor_classificacao["Classe"],
    })
    salvo = classificacao.salvar_classificacao_manual(CAMINHO_CLASSIFICACAO, novo_manual)
    st.success(f"Classificação salva — {len(salvo)} ativos.")
