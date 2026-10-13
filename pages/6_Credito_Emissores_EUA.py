import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from market_lib import sec_edgar  # noqa: E402
from market_lib.estilo import GOLD, NAVY, aplicar_estilo, mostrar_logo_sidebar  # noqa: E402

st.set_page_config(page_title="Dash Offshore — Emissores (EUA)", layout="wide", page_icon="🩺")
aplicar_estilo()
mostrar_logo_sidebar()

st.title("Emissores (EUA) — números divulgados")
st.caption(
    "Demonstrações dos emissores dos bonds da base, **exatamente como as empresas arquivaram na SEC** "
    "(10-K e 10-Q, dados XBRL). Nenhum indicador é calculado aqui — só mudamos a unidade pra US$ milhões. "
    "Cada coluna tem o link do arquivamento de origem pra conferir direto na SEC. As setas ▲▼ só comparam "
    "o número com o do mesmo período do ano anterior."
)

CAMINHO_MAPA = RAIZ_PROJETO / "data" / "emissores_sec.csv"
VERDE, VERMELHO, CINZA = "#1b7a3d", "#b3261e", "#7a7a7a"

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
    resultados, erros = sec_edgar.carregar_varios(tuple(ciks), sec_edgar.VERSAO_DADOS)

if erros:
    st.warning("Não consegui buscar na SEC: " + "; ".join(f"CIK {c} ({e})" for c, e in erros.items()))

fmt = sec_edgar.formatar_mm


def _seta(d):
    return "" if d is None or pd.isna(d) else {1: "▲", -1: "▼", 0: "▬"}[int(d)]


def _cor(d, polaridade):
    """Verde = a mudança ajuda o crédito, vermelho = piora, cinza = neutro/contexto ou estável."""
    if d is None or pd.isna(d) or d == 0 or polaridade is None:
        return CINZA
    return VERDE if (d > 0) == polaridade else VERMELHO


PALAVRA = {1: "Higher", -1: "Lower", 0: "Flat"}


def _celula_yoy(d, polaridade, com_palavra=True):
    """(texto, css) da coluna de variação: seta (+ palavra) colorida; vazio se não há comparação."""
    seta = _seta(d)
    if not seta:
        return "", ""
    texto = f"{seta} {PALAVRA[int(d)]}" if com_palavra else seta
    return texto, f"color: {_cor(d, polaridade)}; font-weight: 600"


# ---------- Visão geral ----------

# coluna -> (chave no resumo, polaridade: True = subir é bom)
COLUNAS_GERAL = {
    "Receita (US$ mm)": ("receita", True), "Lucro líquido (US$ mm)": ("lucro_liquido", True),
    "Caixa operacional (US$ mm)": ("fco", True), "Caixa (US$ mm)": ("caixa", True),
    "Ativo total (US$ mm)": ("ativo_total", None), "Patrimônio líquido (US$ mm)": ("patrimonio", True),
}


def _tabela_geral():
    linhas, estilos = [], []
    for _, m in auto.iterrows():
        d = resultados.get(int(m["CIK"]))
        if d is None or d["sem_us_gaap"]:
            continue
        r = d["resumo"]
        obs = " | ".join(t for t in (m["Nota"], d["defasagem"]) if t)
        linha = {
            "Emissor": m["Emissor"], "Tipo": "Banco / financeira" if d["financeira"] else "Empresa",
            "Documento": sec_edgar.link_arquivamento(d["cik"], r["accn"]), "Form": r["form"],
            "Período": r["periodo"], "Base": r["base"], "Base do caixa op.": r["fco_base"],
        }
        css = {}
        for coluna, (chave, pol) in COLUNAS_GERAL.items():
            linha[coluna] = fmt(r[chave])  # o número, exatamente como arquivado
            if pol is not None:  # coluna ao lado: subiu ou caiu contra o mesmo período do ano anterior
                linha[coluna + " YoY"], css[coluna + " YoY"] = _celula_yoy(r.get(chave + "_dir"), pol, com_palavra=False)
        linha["Bonds na base"], linha["Observações"] = bonds_por_emissor.get(m["Emissor"], np.nan), obs
        linhas.append(linha)
        estilos.append(css)
    df = pd.DataFrame(linhas)
    css = pd.DataFrame(estilos).reindex(columns=df.columns).fillna("")
    ordem = df["Emissor"].argsort().to_numpy()
    return df.iloc[ordem].reset_index(drop=True), css.iloc[ordem].reset_index(drop=True)


FORMATO_GERAL = {
    "Documento": st.column_config.LinkColumn("Documento (SEC)", display_text="Abrir ↗"),
    "Período": st.column_config.DateColumn("Período", format="DD/MM/YYYY"),
    "Bonds na base": st.column_config.NumberColumn(format="%d"),
    **{c + " YoY": st.column_config.TextColumn("YoY", width="small", help="Contra o mesmo período do ano anterior")
       for c, (_, pol) in COLUNAS_GERAL.items() if pol is not None},
}

aba_geral, aba_detalhe = st.tabs(["📋 Visão geral", "🔎 Demonstrações do emissor"])

with aba_geral:
    geral, css_geral = _tabela_geral()
    st.markdown("###### Último arquivamento de cada emissor")
    st.caption(
        "Valores do último 10-Q (resultado dos **3 meses** do trimestre) ou 10-K (**ano fiscal**), conforme o "
        "mais recente; caixa, ativo e patrimônio são do fim do período. **Caixa operacional** é o acumulado do "
        "ano (ex.: 6M YTD) — o 10-Q não traz o trimestre isolado. A coluna **YoY** ao lado de cada número mostra "
        "se subiu (▲) ou caiu (▼) contra o mesmo período do ano anterior (verde = favorável ao crédito, "
        "vermelho = desfavorável). Banco/financeira: "
        "a receita é líquida de juros pagos. 'Abrir ↗' leva ao arquivamento no EDGAR."
    )
    with st.container(border=True):
        st.dataframe(
            geral.style.apply(lambda _: css_geral, axis=None), column_config=FORMATO_GERAL, width="stretch",
            hide_index=True, height=640, placeholder="n/a",
        )

    sem = mapa[mapa["Tipo"] != "Auto"].copy()
    if not sem.empty:
        st.markdown("###### Sem tabelas automáticas")
        sem["Bonds na base"] = sem["Emissor"].map(bonds_por_emissor)
        ultimos, links = [], []
        for _, m in sem.iterrows():
            texto, link = "", None
            if m["CIK"]:
                try:
                    p = sec_edgar.buscar_perfil(int(m["CIK"]), sec_edgar.VERSAO_DADOS)
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
    "Cash flow — year-to-date (10-Q)": "caixa_acum",
    "Cash flow — annual (10-K)": "caixa_anual",
    "Income statement & balance sheet — quarterly (10-Q)": "trimestre",
    "Income statement & balance sheet — annual (10-K)": "anual",
}
LEGENDA = {
    "caixa_acum": (
        "Cumulative cash flow of the year as filed in each 10-Q (3, 6 or 9 months) — the 10-Q does not publish the "
        "cash flow of the quarter alone. Compare columns of the same length (6M with 6M); the arrows already do. "
        "'(cash out)' lines are filed as positive numbers and mean cash leaving the company. Interest paid in cash is only tagged in the annual 10-K by most companies; the interest expense line is shown in both."
    ),
    "caixa_anual": "Full-year cash flow of each 10-K. '(cash out)' lines are filed as positive numbers and mean cash leaving the company.",
    "trimestre": (
        "Result of the three months of each 10-Q, and the balance sheet at the end of the quarter. The 4th quarter "
        "is not filed on its own (it is inside the 10-K and the earnings release)."
    ),
    "anual": "Full-year figures of each 10-K; balance sheet at the fiscal year-end.",
}
COL_YOY = "YoY"
SETAS_LEGENDA = (
    "**Latest vs year ago** = whether the most recent column is higher (▲), lower (▼) or flat (▬, within 1%) than the "
    "same period one year earlier — the two filed numbers are just compared, nothing is calculated. **Green** = "
    "favorable for a bondholder (e.g. more operating cash, less debt, less interest), **red** = unfavorable, "
    "**gray** = neutral/context (capex, issuance, repayments, dividends...)."
)


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


def _grafico_caixa(t, visao):
    """Barras dos três totais do fluxo de caixa (operacional, investimento, financiamento), como arquivados."""
    series = [(c, n, cor) for c, n, cor in (("fco", "Operating", NAVY), ("fci", "Investing", GOLD),
                                              ("fcf_total", "Financing", "#8a8d93")) if c in t["chaves"]]
    if not series:
        return
    colunas = list(t["num"].columns)
    manter = [k for k in range(len(colunas)) if t["dias"][k] and abs(t["dias"][k] - t["dias"][0]) <= 10]
    manter = list(reversed(manter))  # mais antigo -> mais recente
    if len(manter) < 2:
        return
    fig = go.Figure()
    for chave, nome, cor in series:
        i = t["chaves"].index(chave)
        fig.add_bar(name=nome, x=[colunas[k] for k in manter], y=[t["num"].iloc[i, k] / 1e6 for k in manter], marker_color=cor,
                    hovertemplate="%{x}<br>" + nome + ": %{y:,.0f}<extra></extra>")
    titulo = "Cash flow by activity (US$ mm) — same period of each year, as filed" if visao == "caixa_acum" \
        else "Cash flow by activity (US$ mm) — by fiscal year, as filed"
    fig.update_layout(title=titulo, barmode="group", height=320, margin=dict(t=45, b=10, l=10, r=10),
                      legend=dict(orientation="h", y=-0.15))
    fig.add_hline(y=0, line_color="#999999", line_width=1)
    st.plotly_chart(fig, width="stretch")


def _mostrar_tabela(t):
    texto, dirs, pol = t["texto"], t["direcao"], t["polaridade"]
    periodos = list(texto.columns[3:])
    # os números ficam exatamente como arquivados; a coluna ao lado do período mais recente diz se
    # subiu ou caiu contra o mesmo período do ano anterior
    exibido = texto.copy()
    css = pd.DataFrame("", index=texto.index, columns=texto.columns)
    exibido[COL_YOY], css[COL_YOY] = "", ""
    for i in range(len(texto)):
        exibido.at[i, COL_YOY], css.at[i, COL_YOY] = _celula_yoy(dirs.at[i, periodos[0]], pol[i])
    ordem = ["Statement", "Line item", periodos[0], COL_YOY, *periodos[1:], "XBRL tag"]
    exibido, css = exibido[ordem], css[ordem]
    st.dataframe(
        exibido.style.apply(lambda _: css, axis=None), width="stretch", hide_index=True, placeholder="n/a",
        height=min(36 * (len(exibido) + 1) + 3, 900),
        column_config={"Statement": st.column_config.TextColumn(width="medium"),
                       "Line item": st.column_config.TextColumn(width="large", pinned=True),
                       COL_YOY: st.column_config.TextColumn("Latest vs year ago", width="small")},
    )


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
    t, fontes = d["tabelas"][visao], d["fontes"][visao]
    if t is None or t["texto"].empty:
        st.info("Sem dados dessa visão nos arquivamentos da SEC (a empresa pode usar tags próprias) — "
                "abra o arquivamento pelos links acima.")
        return
    if visao.startswith("caixa"):
        _grafico_caixa(t, visao)
    st.markdown("###### As filed — US$ millions")
    with st.container(border=True):
        _mostrar_tabela(t)
    st.caption(SETAS_LEGENDA)
    st.caption(
        LEGENDA[visao] + " **n/a** = the company did not file that line as a standard us-gaap tag for the period "
        "(or does not have it) — open the filing to see it. Debt is shown line by line, exactly as tagged, because "
        "each company breaks it down differently (nothing is added up). 'XBRL tag' is the us-gaap tag the value comes from."
    )

    colunas = list(t["texto"].columns[3:])
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
                    extra = sec_edgar.carregar_empresa(int(opcoes[nome_escolhido]), sec_edgar.VERSAO_DADOS)
                st.subheader(nome_escolhido)
                _detalhe(extra, "busca")
