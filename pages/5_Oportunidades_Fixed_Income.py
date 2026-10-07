import io
import math
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from market_lib import bond_run  # noqa: E402
from market_lib.estilo import GOLD, NAVY, aplicar_estilo, mostrar_logo_sidebar  # noqa: E402

st.set_page_config(page_title="Dash Offshore — Oportunidades Fixed Income", layout="wide", page_icon="🎯")
aplicar_estilo()
mostrar_logo_sidebar()

st.title("Fixed Income — Oportunidades de Alocação")
st.caption(
    "Sobe o bond run (PDF) da Avenue e/ou do BTG Pactual, junta tudo numa tabela só e "
    "filtra por YTW, rating, prazo, duration, setor etc. pra achar a melhor oportunidade. "
    "Quando o mesmo bond aparece nas duas listas, mostra o preço/YTW de cada casa lado a lado."
)

TREASURIES = ["United States of America", "US Treasury TIPS"]


@st.cache_data(show_spinner=False)
def _ler_avenue(conteudo: bytes):
    return bond_run.carregar_run_avenue(io.BytesIO(conteudo))


@st.cache_data(show_spinner=False)
def _ler_btg(conteudo: bytes):
    return bond_run.carregar_run_btg(io.BytesIO(conteudo))


st.sidebar.header("1. Subir os bond runs (PDF)")
arquivo_avenue = st.sidebar.file_uploader("Bond run — Avenue (bonds_list_us.pdf)", type=["pdf"], key="op_avenue")
arquivo_btg = st.sidebar.file_uploader("Bond run — BTG Pactual (US IG List .pdf)", type=["pdf"], key="op_btg")

if arquivo_avenue is None and arquivo_btg is None:
    st.info("Suba pelo menos um dos PDFs na barra lateral pra começar.")
    st.stop()

with st.spinner("Lendo os PDFs (pode levar alguns segundos)..."):
    ave_df, data_ave, nao_ave = _ler_avenue(arquivo_avenue.getvalue()) if arquivo_avenue else (None, None, [])
    btg_df, data_btg, nao_btg = _ler_btg(arquivo_btg.getvalue()) if arquivo_btg else (None, None, [])

data_ref = data_ave or data_btg
if data_ave and data_btg and data_ave != data_btg:
    st.warning(
        f"As duas listas são de datas diferentes (Avenue: {data_ave:%d/%m/%Y} · BTG: "
        f"{data_btg:%d/%m/%Y}) — a comparação entre casas pode estar defasada."
    )
for nome, nao_lidas in (("Avenue", nao_ave), ("BTG", nao_btg)):
    if nao_lidas:
        st.warning(f"{len(nao_lidas)} linha(s) do PDF da {nome} não foram lidas (formato diferente do esperado).")
        with st.expander(f"Ver as linhas da {nome} que não foram lidas"):
            st.code("\n".join(nao_lidas))

base = bond_run.consolidar_runs(ave_df, btg_df, data_ref)
if base.empty:
    st.warning("Não encontrei nenhum bond nos PDFs subidos.")
    st.stop()

n_ave = 0 if ave_df is None else len(ave_df)
n_btg = 0 if btg_df is None else len(btg_df)
nas_duas = base[base["Fontes"] == "Avenue + BTG"]
st.caption(
    f"Avenue: {n_ave} bonds · BTG: {n_btg} bonds · {len(nas_duas)} nas duas listas · "
    f"referência {data_ref:%d/%m/%Y}" if data_ref else f"Avenue: {n_ave} bonds · BTG: {n_btg} bonds"
)

if not nas_duas.empty:
    with st.container(border=True):
        st.markdown("###### Mesmo bond nas duas casas")
        btg_melhor = int((nas_duas["Casa"] == "BTG").sum())
        col1, col2, col3 = st.columns(3)
        col1.metric("Bonds nas duas listas", len(nas_duas))
        col2.metric("BTG com YTW maior em", f"{btg_melhor} de {len(nas_duas)}")
        col3.metric(
            "Diferença média de YTW (BTG − Avenue)",
            f"{nas_duas['Dif. YTW BTG−Avenue (bps)'].mean():+.0f} bps",
            help="Positivo = o BTG está oferecendo o mesmo bond com YTW maior (preço menor).",
        )
        st.caption(
            "Preços e yields dos dois PDFs são indicativos e podem refletir markups/horários "
            "diferentes de cada casa — confirme a cotação ao vivo antes de operar."
        )

# ---------- Filtros ----------

ESCALA_FILTRO = bond_run.ESCALA_RATING[: bond_run.ESCALA_RATING.index("B-") + 1]
prazo_max = math.ceil(base["Prazo (anos)"].max()) if base["Prazo (anos)"].notna().any() else 1
duration_max = math.ceil(base["Duration"].max()) if base["Duration"].notna().any() else 1
ytw_max = math.ceil(base["YTW"].max()) if base["YTW"].notna().any() else 1
tem_curva = base["Spread vs UST (bps)"].notna().any()

with st.container(border=True):
    st.markdown("###### Filtros")
    c1, c2, c3 = st.columns(3)
    with c1:
        casas_disponiveis = [c for c, n in (("Avenue", n_ave), ("BTG", n_btg)) if n]
        casas = st.multiselect("Oferecido por", casas_disponiveis, default=casas_disponiveis, key="op_casas")
        so_nas_duas = st.checkbox(
            "Só bonds que estão nas duas listas", value=False, key="op_so_duas",
            disabled=len(nas_duas) == 0,
        )
        incluir_treasuries = st.checkbox("Incluir Treasuries (referência)", value=False, key="op_tsy")
    with c2:
        criterio = st.radio(
            "Critério de rating",
            ["Pior nota disponível (conservador)", "Nota de referência"],
            key="op_criterio",
            help="Pior nota: a mais baixa entre Avenue e as 3 agências do BTG (Moody's/S&P/Fitch). "
            "Nota de referência: a da Avenue (composta) ou, se o bond só está no BTG, S&P → Fitch → Moody's.",
        )
        rating_min = st.select_slider(
            "Rating mínimo", options=ESCALA_FILTRO + ["Qualquer"], value="Qualquer", key="op_rating_min"
        )
    with c3:
        ytw_min = st.slider("YTW mínimo (%)", 0.0, float(ytw_max), 0.0, 0.1, key="op_ytw_min")
        prazo = st.slider("Prazo até o vencimento (anos)", 0.0, float(prazo_max), (0.0, float(prazo_max)), 0.5, key="op_prazo")
        duration = st.slider("Duration (anos)", 0.0, float(duration_max), (0.0, float(duration_max)), 0.5, key="op_duration")

    c4, c5, c6, c7 = st.columns(4)
    with c4:
        setores = st.multiselect("Setor", sorted(base["Setor"].dropna().unique()), key="op_setores")
    with c5:
        senioridades = st.multiselect(
            "Senioridade", sorted(base["Senioridade"].dropna().unique()), key="op_senioridade",
            help="Só a Avenue informa senioridade — bonds que só estão no BTG ficam de fora quando você filtra por aqui.",
        )
    with c6:
        minimo_opcoes = {"Qualquer": None, "até US$ 2.000": 2000, "até US$ 50.000": 50000, "até US$ 100.000": 100000}
        minimo_escolha = st.selectbox("Mínimo de aplicação", list(minimo_opcoes), key="op_minimo")
    with c7:
        busca = st.text_input("Emissor, ticker ou CUSIP contém", key="op_busca")

# ---------- Aplica filtros ----------

f = base.copy()
usar_pior = criterio.startswith("Pior")
f["Nota"] = f["Nota (pior)"] if usar_pior else f["Nota (referência)"]
f["Rating (critério)"] = f["Nota"].map(bond_run.rotulo_rating)

mascara = pd.Series(True, index=f.index)
if casas:
    mascara &= f["Fontes"].apply(lambda s: any(c in s for c in casas))
else:
    mascara &= False
if so_nas_duas:
    mascara &= f["Fontes"] == "Avenue + BTG"
if not incluir_treasuries:
    mascara &= ~f["Emissor"].isin(TREASURIES)
if rating_min != "Qualquer":
    mascara &= f["Nota"] <= bond_run.score_rating(rating_min)
mascara &= f["YTW"] >= ytw_min
mascara &= f["Prazo (anos)"].between(prazo[0], prazo[1]) | (f["Prazo (anos)"].isna() & (prazo[1] >= prazo_max))
mascara &= f["Duration"].between(duration[0], duration[1])
if setores:
    mascara &= f["Setor"].isin(setores)
if senioridades:
    mascara &= f["Senioridade"].isin(senioridades)
limite_minimo = minimo_opcoes[minimo_escolha]
if limite_minimo:
    mascara &= f["Mínimo (US$)"].isna() | (f["Mínimo (US$)"] <= limite_minimo)
if busca.strip():
    termo = busca.strip().lower()
    mascara &= (
        f["Emissor"].str.lower().str.contains(termo, na=False, regex=False)
        | f["Ticker"].str.lower().str.contains(termo, na=False, regex=False)
        | f["CUSIP"].str.lower().str.contains(termo, na=False, regex=False)
    )

filtrado = f[mascara].copy()

if filtrado.empty:
    st.info("Nenhum bond passa nesses filtros — afrouxa algum critério acima.")
    st.stop()

opcoes_ordem = ["Spread vs Treasury (maior primeiro)", "YTW (maior primeiro)"] if tem_curva else ["YTW (maior primeiro)"]
ordem = st.radio("Ordenar por", opcoes_ordem, horizontal=True, key="op_ordem")
coluna_ordem = "Spread vs UST (bps)" if ordem.startswith("Spread") else "YTW"
filtrado = filtrado.sort_values(coluna_ordem, ascending=False, na_position="last").reset_index(drop=True)

col1, col2, col3, col4 = st.columns(4)
with col1, st.container(border=True):
    st.metric("Bonds que passam nos filtros", len(filtrado))
with col2, st.container(border=True):
    st.metric("Maior YTW", f"{filtrado['YTW'].max():.2f}%")
with col3, st.container(border=True):
    st.metric("YTW médio", f"{filtrado['YTW'].mean():.2f}%")
with col4, st.container(border=True):
    if tem_curva and filtrado["Spread vs UST (bps)"].notna().any():
        st.metric(
            "Spread médio vs Treasury", f"{filtrado['Spread vs UST (bps)'].mean():.0f} bps",
            help="YTW menos o YTW dos Treasuries da lista da Avenue na mesma duration (curva interpolada, aproximada).",
        )
    else:
        st.metric("Duration média", f"{filtrado['Duration'].mean():.1f} anos")

if not tem_curva:
    st.caption(
        "Spread vs Treasury só aparece com o PDF da Avenue — a curva de Treasuries vem da lista dela."
    )

# ---------- Tabelas ----------

CONFIG_COLUNAS = {
    "Cupom": st.column_config.NumberColumn("Cupom (%)", format="%.3f"),
    "Vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
    "Prazo (anos)": st.column_config.NumberColumn("Prazo (anos)", format="%.1f"),
    "Duration": st.column_config.NumberColumn("Duration", format="%.2f"),
    "YTW": st.column_config.NumberColumn("YTW", format="%.2f%%"),
    "Spread vs UST (bps)": st.column_config.NumberColumn("Spread vs UST (bps)", format="%.0f"),
    "Preço": st.column_config.NumberColumn("Preço", format="%.2f"),
    "YTW Avenue": st.column_config.NumberColumn("YTW Avenue", format="%.2f%%"),
    "YTW BTG": st.column_config.NumberColumn("YTW BTG", format="%.2f%%"),
    "Dif. YTW BTG−Avenue (bps)": st.column_config.NumberColumn("BTG − Avenue (bps)", format="%+.0f"),
    "Proxima Chamada": st.column_config.DateColumn("Próx. chamada", format="DD/MM/YYYY"),
    "Mínimo (US$)": st.column_config.NumberColumn("Mínimo (US$)", format="localized"),
}


def _para_exibir(df, colunas):
    saida = df[[c for c in colunas if c in df.columns]].copy()
    for coluna in ("Vencimento", "Proxima Chamada"):
        if coluna in saida:
            saida[coluna] = pd.to_datetime(saida[coluna])
    return saida


st.markdown("")
st.subheader("Melhores oportunidades")
st.caption(f"As 15 primeiras da lista filtrada, ordenadas por {ordem.split(' (')[0]}.")
with st.container(border=True):
    st.dataframe(
        _para_exibir(
            filtrado.head(15),
            ["Emissor", "Ticker", "Cupom", "Vencimento", "Duration", "YTW", "Spread vs UST (bps)",
             "Casa", "Preço", "Rating (critério)", "Setor"],
        ),
        column_config=CONFIG_COLUNAS, width="stretch", hide_index=True, height=565,
    )

st.markdown("")
st.subheader("YTW × Duration")
filtrado["Faixa de rating"] = pd.cut(
    filtrado["Nota"], [0, 4, 7, 10, 25], labels=["AA ou melhor", "A", "BBB", "BB ou pior"]
).astype(object).where(filtrado["Nota"].notna(), "Sem rating")
filtrado["Vencimento (texto)"] = pd.to_datetime(filtrado["Vencimento"]).dt.strftime("%d/%m/%Y").fillna("perpétuo")
fig = px.scatter(
    filtrado, x="Duration", y="YTW", color="Faixa de rating",
    color_discrete_map={
        "AA ou melhor": NAVY, "A": GOLD, "BBB": "#5B7B7A", "BB ou pior": "#b3261e", "Sem rating": "#999999",
    },
    category_orders={"Faixa de rating": ["AA ou melhor", "A", "BBB", "BB ou pior", "Sem rating"]},
    hover_data={
        "Emissor": True, "Ticker": True, "Cupom": ":.3f", "Vencimento (texto)": True, "YTW": ":.2f",
        "Duration": ":.2f", "Casa": True, "Faixa de rating": False,
    },
    opacity=0.75,
)
curva = bond_run.curva_treasury(ave_df)
if curva is not None:
    fig.add_trace(go.Scatter(
        x=curva["Duration"], y=curva["YTW"], mode="lines+markers", name="Treasuries (Avenue)",
        line=dict(color="#444444", dash="dot"), marker=dict(size=5),
    ))
fig.update_traces(marker=dict(size=7), selector=dict(mode="markers"))
fig.update_layout(
    margin=dict(t=10, b=10, l=10, r=10), height=420, xaxis_title="Duration (anos)", yaxis_title="YTW (%)",
    legend_title_text="",
)
with st.container(border=True):
    st.plotly_chart(fig, width="stretch")

st.markdown("")
st.subheader("Todos os bonds filtrados")
with st.container(border=True):
    st.dataframe(
        _para_exibir(
            filtrado,
            ["Emissor", "Ticker", "Cupom", "Vencimento", "Prazo (anos)", "Duration", "YTW",
             "Spread vs UST (bps)", "Casa", "Preço", "YTW Avenue", "YTW BTG", "Dif. YTW BTG−Avenue (bps)",
             "Rating (critério)", "Rating Avenue", "Ratings BTG (Moody's/S&P/Fitch)", "Setor",
             "Senioridade", "Proxima Chamada", "Mínimo (US$)", "Tipo de Cupom", "CUSIP"],
        ),
        column_config=CONFIG_COLUNAS, width="stretch", hide_index=True, height=520,
    )
st.caption(
    "YTW (yield to worst) e duration são os da lista da casa com o melhor YTW; no BTG usa-se o "
    "YTW do lado Ask (o que o comprador paga). Mínimo da Avenue = quantidade × US$ 1.000. "
    "Tipo de cupom 'VARIABLE' (BTG) são bonds de cupom variável/fixo-para-flutuante — o YTW "
    "deles considera a data de chamada. Os dados são indicativos, direto dos PDFs."
)
