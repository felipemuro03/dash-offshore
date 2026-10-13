import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from market_lib import sec_edgar  # noqa: E402
from market_lib.estilo import aplicar_estilo, mostrar_logo_sidebar  # noqa: E402

st.set_page_config(page_title="Dash Offshore — Emissores (EUA)", layout="wide", page_icon="🩺")
aplicar_estilo()
mostrar_logo_sidebar()

st.title("Emissores (EUA) — números divulgados")
st.caption(
    "Demonstrações dos emissores dos bonds da base, **exatamente como as empresas arquivaram na SEC** "
    "(10-K e 10-Q, dados XBRL). Nenhum indicador é calculado aqui — só mudamos a unidade pra US$ milhões. "
    "Cada coluna tem o link do arquivamento de origem pra conferir direto na SEC."
)

CAMINHO_MAPA = RAIZ_PROJETO / "data" / "emissores_sec.csv"

st.sidebar.header("Opcional")
arquivo_excel = st.sidebar.file_uploader(
    "Emissores - EUA (.xlsx)", type=["xlsx"], key="ce_excel",
    help="Planilha com CUSIP, Description e Emissor dos bonds da base — só pra mostrar quantos bonds "
    "temos de cada emissor e avisar se aparecer emissor sem mapeamento.",
)
if st.sidebar.button("🔄 Atualizar dados da SEC", help="Ignora o cache de 6 horas e busca tudo de novo."):
    for funcao in (sec_edgar.carregar_varios, sec_edgar.carregar_empresa, sec_edgar.buscar_perfil,
                   sec_edgar.listar_registrantes):
        funcao.clear()
    st.rerun()

mapa = pd.read_csv(CAMINHO_MAPA, dtype=str).fillna("")

bonds_por_emissor, cusips_por_emissor = {}, {}
if arquivo_excel is not None:
    bonds = pd.read_excel(arquivo_excel, dtype=str).dropna(subset=["CUSIP", "Emissor"])
    bonds = bonds.drop_duplicates("CUSIP")
    bonds_por_emissor = bonds.groupby("Emissor")["CUSIP"].nunique().to_dict()
    cusips_por_emissor = {e: g[["CUSIP", "Description"]] for e, g in bonds.groupby("Emissor")}
    sem_mapa = sorted(set(bonds["Emissor"]) - set(mapa["Emissor"]))
    if sem_mapa:
        st.warning(
            "Emissores da planilha sem mapeamento em `data/emissores_sec.csv` (não aparecem na análise): "
            + "; ".join(sem_mapa)
        )

# ---------- carga dos dados da SEC ----------

auto = mapa[(mapa["Tipo"] == "Auto") & (mapa["CIK"] != "")]
ciks = sorted({int(c) for c in auto["CIK"]})
with st.spinner(f"Buscando as demonstrações de {len(ciks)} empresas na SEC (~30 s na primeira vez; depois fica em cache)..."):
    resultados, erros = sec_edgar.carregar_varios(tuple(ciks))

if erros:
    st.warning("Não consegui buscar na SEC: " + "; ".join(f"CIK {c} ({e})" for c, e in erros.items()))


fmt = sec_edgar.formatar_mm


def _tabela_geral():
    linhas = []
    for _, m in auto.iterrows():
        d = resultados.get(int(m["CIK"]))
        if d is None or d["sem_us_gaap"]:
            continue
        r = d["resumo"]
        obs = " | ".join(t for t in (m["Nota"], d["defasagem"]) if t)
        linhas.append({
            "Emissor": m["Emissor"], "Tipo": "Banco / financeira" if d["financeira"] else "Empresa",
            "Documento": sec_edgar.link_arquivamento(d["cik"], r["accn"]), "Form": r["form"],
            "Período": r["periodo"], "Base": r["base"],
            "Receita (US$ mm)": fmt(r["receita"]), "Lucro líquido (US$ mm)": fmt(r["lucro_liquido"]),
            "Caixa (US$ mm)": fmt(r["caixa"]),
            "Ativo total (US$ mm)": fmt(r["ativo_total"]), "Patrimônio líquido (US$ mm)": fmt(r["patrimonio"]),
            "Bonds na base": bonds_por_emissor.get(m["Emissor"], np.nan), "Observações": obs,
        })
    return pd.DataFrame(linhas).sort_values("Emissor").reset_index(drop=True)


FORMATO_GERAL = {
    "Documento": st.column_config.LinkColumn("Documento (SEC)", display_text="Abrir ↗"),
    "Período": st.column_config.DateColumn("Período", format="DD/MM/YYYY"),
    "Bonds na base": st.column_config.NumberColumn(format="%d"),
}

aba_geral, aba_detalhe = st.tabs(["📋 Visão geral", "🔎 Demonstrações do emissor"])

# ---------- Visão geral ----------

with aba_geral:
    geral = _tabela_geral()
    st.markdown("###### Último arquivamento de cada emissor")
    st.caption(
        "Valores do último 10-Q (resultado dos **3 meses** do trimestre) ou 10-K (**ano fiscal**), conforme o "
        "mais recente; caixa, ativo e patrimônio são do fim do período. Banco/financeira: a receita é a "
        "receita líquida de juros pagos. 'Abrir ↗' leva ao arquivamento no EDGAR. Pra ver as linhas completas "
        "(dívida, juros, fluxo de caixa...), use a aba ao lado."
    )
    with st.container(border=True):
        st.dataframe(geral, column_config=FORMATO_GERAL, width="stretch", hide_index=True, height=640,
                     placeholder="n/a")

    sem = mapa[mapa["Tipo"] != "Auto"].copy()
    if not sem.empty:
        st.markdown("###### Sem tabelas automáticas")
        sem["Bonds na base"] = sem["Emissor"].map(bonds_por_emissor)
        ultimos, links = [], []
        for _, m in sem.iterrows():
            texto, link = "", None
            if m["CIK"]:
                try:
                    p = sec_edgar.buscar_perfil(int(m["CIK"]))
                    arq = p["ultimos_arquivamentos"][0] if p["ultimos_arquivamentos"] else None
                    if arq:
                        texto = f"{arq['form']} de {arq['filed']:%d/%m/%Y}"
                        link = sec_edgar.link_arquivamento(int(m["CIK"]), arq["accn"])
                except Exception:  # noqa: BLE001
                    pass
            ultimos.append(texto)
            links.append(link)
        sem["Último arquivamento"], sem["Documento"] = ultimos, links
        with st.container(border=True):
            st.dataframe(
                sem[["Emissor", "Tipo", "Último arquivamento", "Documento", "Nota", "Bonds na base"]],
                column_config={"Bonds na base": st.column_config.NumberColumn(format="%d"),
                               "Documento": st.column_config.LinkColumn("Documento (SEC)", display_text="Abrir ↗")},
                width="stretch", hide_index=True, placeholder="—",
            )

# ---------- Demonstrações ----------

VISOES = {
    "Quarterly (10-Q) — three months ended": "trimestre",
    "Year-to-date (10-Q) — cumulative": "acumulado",
    "Annual (10-K) — year ended": "anual",
}
LEGENDA = {
    "trimestre": (
        "Result of the three months of each 10-Q, and the balance sheet at the end of the quarter. The 4th quarter "
        "is not filed on its own (it is inside the 10-K and the earnings release), and the cash flow statement in a "
        "10-Q is only cumulative — see the year-to-date view."
    ),
    "acumulado": (
        "Cumulative figures of the year as filed in each 10-Q (3, 6 or 9 months); the cash flow statement is only "
        "published this way. Balance sheet at the end of the period."
    ),
    "anual": "Full-year figures of each 10-K; balance sheet at the fiscal year-end.",
}


def _links(d, perfil):
    cik = d["cik"]
    partes = [f"[All 10-K / 10-Q on EDGAR ↗]({sec_edgar.link_empresa(cik)})"]
    if d["resumo"]:
        partes.append(f"[Latest filing ({d['resumo']['form']}, {d['resumo']['periodo']:%b %d, %Y}) ↗]"
                      f"({sec_edgar.link_arquivamento(cik, d['resumo']['accn'])})")
    if perfil["site"]:
        site = perfil["site"] if perfil["site"].startswith("http") else "https://" + perfil["site"]
        partes.append(f"[Company website ↗]({site})")
    st.markdown("  ·  ".join(partes))
    if perfil["releases"]:
        releases = ", ".join(f"[{r['filed']:%b %d, %Y} ↗]({sec_edgar.link_arquivamento(cik, r['accn'])})"
                             for r in perfil["releases"])
        st.markdown(f"**Earnings releases** (8-K item 2.02; the release is the EX-99.1 exhibit in each filing): {releases}")


def _detalhe(d, chave):
    perfil = d["perfil"]
    if d["sem_us_gaap"]:
        st.warning("Sem dados XBRL us-gaap para essa empresa — veja os arquivamentos no EDGAR.")
        st.markdown(f"[All filings on EDGAR ↗]({sec_edgar.link_empresa(d['cik'], '')})")
        return
    if d["defasagem"]:
        st.warning(d["defasagem"])
    st.caption(
        f"{perfil['nome_sec']} · SIC {perfil['sic']} {perfil['sic_descricao']} · "
        f"tickers: {', '.join(perfil['tickers']) or '—'} · fim do ano fiscal: {perfil['fim_ano_fiscal']}"
    )
    _links(d, perfil)

    escolha = st.radio("View", list(VISOES), horizontal=True, key=f"ce_visao_{chave}")
    visao = VISOES[escolha]
    tabela, fontes = d["tabelas"][visao], d["fontes"][visao]
    if tabela.empty:
        st.info("Sem arquivamento desse tipo nos dados da SEC.")
        return
    colunas = list(tabela.columns[3:])
    st.markdown("###### As filed — US$ millions")
    with st.container(border=True):
        st.dataframe(
            tabela[["Line item", *colunas, "Statement", "XBRL tag"]], width="stretch", hide_index=True,
            placeholder="n/a", height=min(36 * (len(tabela) + 1) + 3, 900),
            column_config={"Line item": st.column_config.TextColumn(width="large", pinned=True)},
        )
    st.caption(
        LEGENDA[visao] + " **n/a** = the company did not file that line as a standard us-gaap tag for the period "
        "(or does not have it) — open the filing to see it. Debt is shown line by line, exactly as tagged, because "
        "each company breaks it down differently (nothing is added up). 'XBRL tag' is the us-gaap tag the value comes from."
    )

    origem = pd.DataFrame({
        "Column": colunas, "Form": fontes["form"].to_numpy(), "Period end": fontes["periodo"].to_numpy(),
        "Filed on": fontes["filed"].to_numpy(),
        "Filing": [sec_edgar.link_arquivamento(d["cik"], a) for a in fontes["accn"]],
    })
    with st.expander("Source filing of each column", expanded=False):
        st.dataframe(
            origem, hide_index=True, width="stretch",
            column_config={
                "Period end": st.column_config.DateColumn(format="MMM DD, YYYY"),
                "Filed on": st.column_config.DateColumn(format="MMM DD, YYYY"),
                "Filing": st.column_config.LinkColumn("Filing (SEC)", display_text="Open ↗"),
            },
        )
    st.caption(
        "Not shown on purpose: EBITDA, net debt, free cash flow and ratios are not line items companies file — "
        "the figures the company itself publishes for them (adjusted EBITDA, net debt, segment operating income...) "
        "are in the earnings release linked above."
    )


with aba_detalhe:
    emissores_analisaveis = [e for e in auto["Emissor"] if resultados.get(int(auto[auto["Emissor"] == e].iloc[0]["CIK"]))]
    escolha = st.selectbox("Emissor da base", emissores_analisaveis, key="ce_emissor") if emissores_analisaveis else None
    if escolha:
        m = auto[auto["Emissor"] == escolha].iloc[0]
        st.header(escolha)
        if m["Nota"]:
            st.info(m["Nota"])
        _detalhe(resultados[int(m["CIK"])], "base")
        if escolha in cusips_por_emissor:
            st.markdown("###### Bonds na base")
            with st.container(border=True):
                st.dataframe(cusips_por_emissor[escolha], width="stretch", hide_index=True)

    with st.expander("Ver outra empresa (busca por nome na SEC)"):
        termo = st.text_input("Nome da empresa", key="ce_busca")
        if termo.strip():
            registrantes = sec_edgar.listar_registrantes()
            achados = registrantes[registrantes["Nome"].str.contains(termo.strip(), case=False, na=False)].head(30)
            if achados.empty:
                st.caption("Nenhum registrante com esse nome (só aparecem empresas com 10-K/10-Q recentes).")
            else:
                opcoes = {f"{n} (CIK {c})": c for c, n in zip(achados["CIK"], achados["Nome"])}
                nome_escolhido = st.selectbox("Empresa", list(opcoes), key="ce_busca_escolha")
                with st.spinner("Buscando na SEC..."):
                    extra = sec_edgar.carregar_empresa(int(opcoes[nome_escolhido]))
                st.subheader(nome_escolhido)
                _detalhe(extra, "busca")
