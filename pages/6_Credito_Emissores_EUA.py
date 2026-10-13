import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from market_lib import credito_emissores as ce  # noqa: E402
from market_lib import sec_edgar  # noqa: E402
from market_lib.estilo import GOLD, NAVY, aplicar_estilo, mostrar_logo_sidebar  # noqa: E402

st.set_page_config(page_title="Dash Offshore — Crédito dos Emissores", layout="wide", page_icon="🩺")
aplicar_estilo()
mostrar_logo_sidebar()

st.title("Crédito — Saúde dos Emissores (EUA)")
st.caption(
    "Busca direto na SEC (API XBRL pública, 10-K e 10-Q) as demonstrações dos emissores que temos na base "
    "e calcula alavancagem, cobertura de juros, liquidez e fluxo de caixa — pra ver de relance quem "
    "está saudável e quem merece atenção. Os números são os arquivados pelas empresas; o EBITDA é contábil "
    "(resultado operacional + D&A), sem os ajustes de itens não recorrentes que as empresas divulgam."
)

CAMINHO_MAPA = RAIZ_PROJETO / "data" / "emissores_sec.csv"
BI = 1e9

st.sidebar.header("Opcional")
arquivo_excel = st.sidebar.file_uploader(
    "Emissores - EUA (.xlsx)", type=["xlsx"], key="ce_excel",
    help="Planilha com CUSIP, Description e Emissor dos bonds da base — só pra mostrar quantos bonds "
    "temos de cada emissor e avisar se aparecer emissor sem mapeamento.",
)
if st.sidebar.button("🔄 Atualizar dados da SEC", help="Ignora o cache de 6 horas e busca tudo de novo."):
    for funcao in (sec_edgar.carregar_varios, sec_edgar.calcular_metricas, sec_edgar.buscar_perfil, sec_edgar.listar_registrantes):
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
    resultados, erros = sec_edgar.carregar_varios(tuple((c, None) for c in ciks))

if erros:
    st.warning("Não consegui buscar na SEC: " + "; ".join(f"CIK {c} ({e})" for c, e in erros.items()))


def _calcular(cik, perfil_alavancagem="Padrão"):
    """(indicadores, sinais, perfil SEC, tipo, aviso de defasagem, demonstrativo trimestral) de uma empresa."""
    bruto, perfil = resultados[cik] if cik in resultados else sec_edgar.calcular_metricas(cik)
    if bruto.empty:
        return None
    aviso = ce.aviso_defasagem(perfil, bruto)
    tri = ce.formatar_demonstrativo(ce.demonstrativo_trimestral(bruto, perfil["financeira"]))
    if perfil["financeira"]:
        return ce.indicadores_financeira(bruto), None, perfil, "fin", aviso, tri
    ind = ce.indicadores_corporativa(bruto)
    return ind, ce.semaforo_corporativa(ind.iloc[0], perfil_alavancagem), perfil, "corp", aviso, tri


calculados = {}
for _, linha in auto.iterrows():
    cik = int(linha["CIK"])
    if cik in resultados:
        calculados[linha["Emissor"]] = _calcular(cik, linha["Perfil de alavancagem"])

ORDEM_SINAL = {ce.VERMELHO: 0, ce.AMARELO: 1, ce.CINZA: 2, ce.VERDE: 3}


def _tabela_corporativas():
    linhas = []
    for _, m in auto.iterrows():
        r = calculados.get(m["Emissor"])
        if r is None or r[3] != "corp":
            continue
        ind, sinais, perfil, _, aviso, _ = r
        u = ind.iloc[0]
        observacoes = [t for t in (m["Nota"], aviso) if t]
        linhas.append({
            "Sinal": sinais["geral"], "Emissor": m["Emissor"], "Período": u["Fim do período"],
            "Receita (US$ bi)": u["Receita (LTM)"] / BI, "EBITDA (US$ bi)": u["EBITDA (LTM)"] / BI,
            "Margem EBITDA": u["Margem EBITDA"], "Dívida líquida (US$ bi)": u["Dívida líquida"] / BI,
            "Dív. líq./EBITDA": u["Dívida líquida/EBITDA"],
            "Tendência (12m)": ce.tendencia(ind["Dívida líquida/EBITDA"]),
            "Cobertura (EBITDA/juros)": u["Cobertura de juros (EBITDA/juros)"],
            "Liquidez corrente": u["Liquidez corrente"], "FCL (US$ bi)": u["Fluxo de caixa livre (LTM)"] / BI,
            "Bonds na base": bonds_por_emissor.get(m["Emissor"], np.nan),
            "Observações": " | ".join(observacoes),
            "_ordem": ORDEM_SINAL[sinais["geral"]],
        })
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    df["_lev"] = df["Dív. líq./EBITDA"].fillna(-1)
    return df.sort_values(["_ordem", "_lev"], ascending=[True, False]).drop(columns=["_ordem", "_lev"]).reset_index(drop=True)


def _tabela_financeiras():
    linhas = []
    for _, m in auto.iterrows():
        r = calculados.get(m["Emissor"])
        if r is None or r[3] != "fin":
            continue
        ind, _, perfil, _, aviso, _ = r
        u = ind.iloc[0]
        observacoes = [t for t in (m["Nota"], aviso) if t]
        linhas.append({
            "Emissor": m["Emissor"], "Período": u["Fim do período"], "Ativo (US$ bi)": u["Ativo total"] / BI,
            "PL/Ativo": u["PL/Ativo"], "ROE": u["ROE (LTM, PL final)"], "ROA": u["ROA (LTM, ativo final)"],
            "Eficiência": u["Índice de eficiência"], "Provisão/Receita": u["Provisão/Receita"],
            "ROE vs 12m": ce.tendencia(ind["ROE (LTM, PL final)"], melhor_se_menor=False, tolerancia=0.01),
            "Bonds na base": bonds_por_emissor.get(m["Emissor"], np.nan),
            "Observações": " | ".join(observacoes),
        })
    return pd.DataFrame(linhas).sort_values("ROE", ascending=False).reset_index(drop=True) if linhas else pd.DataFrame()


FORMATO = {
    "Período": st.column_config.DateColumn("Dados até", format="DD/MM/YYYY"),
    "Receita (US$ bi)": st.column_config.NumberColumn(format="%.1f"),
    "EBITDA (US$ bi)": st.column_config.NumberColumn(format="%.1f"),
    "Margem EBITDA": st.column_config.NumberColumn(format="percent"),
    "Dívida líquida (US$ bi)": st.column_config.NumberColumn(format="%.1f"),
    "Dív. líq./EBITDA": st.column_config.NumberColumn(format="%.2fx"),
    "Cobertura (EBITDA/juros)": st.column_config.NumberColumn(format="%.1fx"),
    "Liquidez corrente": st.column_config.NumberColumn(format="%.2fx"),
    "FCL (US$ bi)": st.column_config.NumberColumn(format="%.1f"),
    "Ativo (US$ bi)": st.column_config.NumberColumn(format="%.0f"),
    "PL/Ativo": st.column_config.NumberColumn(format="percent"),
    "ROE": st.column_config.NumberColumn(format="percent"),
    "ROA": st.column_config.NumberColumn(format="percent", ),
    "Eficiência": st.column_config.NumberColumn(format="percent"),
    "Provisão/Receita": st.column_config.NumberColumn(format="percent"),
    "Bonds na base": st.column_config.NumberColumn(format="%d"),
}

aba_geral, aba_detalhe = st.tabs(["📋 Visão geral", "🔎 Detalhe do emissor"])

# ---------- Visão geral ----------

with aba_geral:
    corp = _tabela_corporativas()
    if not corp.empty:
        contagem = corp["Sinal"].value_counts()
        c1, c2, c3, c4 = st.columns(4)
        with c1, st.container(border=True):
            st.metric("🔴 Atenção", int(contagem.get(ce.VERMELHO, 0)))
        with c2, st.container(border=True):
            st.metric("🟡 Monitorar", int(contagem.get(ce.AMARELO, 0)))
        with c3, st.container(border=True):
            st.metric("🟢 Saudável", int(contagem.get(ce.VERDE, 0)))
        with c4, st.container(border=True):
            st.metric("⚪ Sem dado suficiente", int(contagem.get(ce.CINZA, 0)))

        st.markdown("###### Empresas (corporativas)")
        filtro = st.multiselect(
            "Filtrar por sinal", [ce.VERMELHO, ce.AMARELO, ce.VERDE, ce.CINZA],
            default=[ce.VERMELHO, ce.AMARELO, ce.VERDE, ce.CINZA], key="ce_filtro_sinal",
        )
        with st.container(border=True):
            st.dataframe(
                corp[corp["Sinal"].isin(filtro)], column_config=FORMATO, width="stretch",
                hide_index=True, height=640,
            )
        with st.expander("Como ler o sinal"):
            st.markdown(
                "O **sinal** é o pior entre **alavancagem** (dívida líquida/EBITDA) e **cobertura de juros** "
                "(EBITDA/despesa de juros); sem alavancagem calculável fica ⚪. É uma regra de bolso pra "
                "priorizar o que olhar — não substitui a análise. Alavancagem **negativa** = caixa líquido "
                "(a empresa tem mais caixa e aplicações do que dívida).\n\n"
                "| Perfil | Alavancagem 🟢 / 🟡 / 🔴 | Cobertura 🟢 / 🟡 / 🔴 |\n|---|---|---|\n"
                "| Padrão | ≤ 2,0x / ≤ 4,0x / acima | ≥ 6x / ≥ 3x / abaixo |\n"
                "| Alavancagem estruturalmente alta (utilities, telecom, cable) | ≤ 4,0x / ≤ 6,0x / acima | ≥ 4x / ≥ 2,5x / abaixo |\n\n"
                "**Limitações que mudam a leitura:** (1) EBITDA contábil = resultado operacional + D&A, sem "
                "somar de volta itens não recorrentes nem remuneração em ações — empresas com baixas grandes "
                "(Goodyear, Ford) ficam subestimadas e o EBITDA ajustado divulgado costuma ser 2–5% maior; "
                "(2) quando a empresa não tem linha de resultado operacional, o EBIT é aproximado por lucro "
                "antes do IR ± juros; (3) a SEC só expõe tags padrão: dívida/juros/D&A em tag própria da "
                "empresa aparecem como n/d (Ford, Caterpillar, T-Mobile e PG&E, por exemplo); (4) Ford e "
                "Caterpillar consolidam o braço financeiro."
            )

    fin = _tabela_financeiras()
    if not fin.empty:
        st.markdown("###### Bancos e financeiras")
        st.caption(
            "Sem semáforo: o certo é comparar entre pares. ROE e ROA usam o patrimônio/ativo do fim do "
            "período (não a média). Índices de capital regulatório (CET1) não estão disponíveis na API da SEC."
        )
        with st.container(border=True):
            st.dataframe(fin, column_config=FORMATO, width="stretch", hide_index=True, placeholder="n/d")

    sem = mapa[mapa["Tipo"] != "Auto"].copy()
    if not sem.empty:
        st.markdown("###### Sem métricas automáticas")
        sem["Bonds na base"] = sem["Emissor"].map(bonds_por_emissor)
        ultimos = []
        for _, m in sem.iterrows():
            if m["CIK"]:
                try:
                    p = sec_edgar.buscar_perfil(int(m["CIK"]))
                    arq = p["ultimos_arquivamentos"][0] if p["ultimos_arquivamentos"] else None
                    ultimos.append(f"{arq[0]} de {pd.Timestamp(arq[1]):%d/%m/%Y}" if arq else "")
                except Exception:  # noqa: BLE001
                    ultimos.append("")
            else:
                ultimos.append("")
        sem["Último arquivamento"] = ultimos
        with st.container(border=True):
            st.dataframe(
                sem[["Emissor", "Tipo", "Último arquivamento", "Nota", "Bonds na base"]],
                column_config={"Bonds na base": st.column_config.NumberColumn(format="%d")},
                width="stretch", hide_index=True, placeholder="—",
            )

# ---------- Detalhe ----------


def _grafico_linha(df, coluna, titulo, formato, linhas_ref=None):
    dados = df.dropna(subset=[coluna]).sort_values("Fim do período")
    if dados.empty:
        st.caption(f"{titulo}: sem dado.")
        return
    fig = go.Figure(go.Scatter(
        x=dados["Fim do período"], y=dados[coluna], mode="lines+markers", line=dict(color=NAVY),
        hovertemplate="%{x|%d/%m/%Y}: %{y:" + formato + "}<extra></extra>",
    ))
    for valor, nome, cor in (linhas_ref or []):
        fig.add_hline(y=valor, line_dash="dot", line_color=cor, annotation_text=nome, annotation_position="top left")
    fig.update_layout(title=titulo, height=300, margin=dict(t=40, b=10, l=10, r=10), showlegend=False)
    st.plotly_chart(fig, width="stretch")


def _trimestral(tri):
    """Numeros do trimestre isolado, em ingles e no formato do earnings release da empresa."""
    st.markdown("###### Quarterly results — as reported (US$ millions, three months ended)")
    with st.container(border=True):
        st.dataframe(tri, width="stretch", placeholder="n/a")
    st.caption(
        "Three-month figures from the 10-Q/10-K XBRL (the 4th quarter = full year minus nine months), laid out "
        "like an earnings release. They tie to the company's release for the standard GAAP lines; non-GAAP "
        "measures (segment operating income, adjusted EBITDA/EPS) are not in the SEC data. Net Debt = Total Debt "
        "minus cash (and short-term investments, when tagged); Free Cash Flow = operating cash flow minus capex "
        "(companies may adjust it, e.g. for insurance recoveries)."
    )


def _detalhe(ind, sinais, perfil, tipo, aviso, perfil_alavancagem, tri):
    if aviso:
        st.warning(aviso)
    u = ind.iloc[0]
    st.caption(
        f"{perfil['nome_sec']} · SIC {perfil['sic']} {perfil['sic_descricao']} · "
        f"tickers: {', '.join(perfil['tickers']) or '—'} · fim do ano fiscal: {perfil['fim_ano_fiscal']} · "
        f"dados até {u['Fim do período']:%d/%m/%Y}"
    )

    def fmt(v, formato):
        return "n/d" if pd.isna(v) else formato.format(v)

    if tipo == "corp":
        cards = [
            ("Receita (LTM)", fmt(u["Receita (LTM)"] / BI, "US$ {:,.1f} bi")),
            ("EBITDA (LTM)", fmt(u["EBITDA (LTM)"] / BI, "US$ {:,.1f} bi")),
            (f"Dív. líq./EBITDA {sinais['alavancagem']}", fmt(u["Dívida líquida/EBITDA"], "{:.2f}x")),
            (f"Cobertura EBITDA/juros {sinais['cobertura']}", fmt(u["Cobertura de juros (EBITDA/juros)"], "{:.1f}x")),
            ("Dívida líquida", fmt(u["Dívida líquida"] / BI, "US$ {:,.1f} bi")),
            (f"Liquidez corrente {sinais['liquidez']}", fmt(u["Liquidez corrente"], "{:.2f}x")),
            (f"Fluxo de caixa livre {sinais['fcl']}", fmt(u["Fluxo de caixa livre (LTM)"] / BI, "US$ {:,.1f} bi")),
            ("Margem EBITDA", fmt(u["Margem EBITDA"] * 100, "{:.1f}%")),
        ]
        colunas = st.columns(4)
        for i, (rotulo, valor) in enumerate(cards):
            with colunas[i % 4], st.container(border=True):
                st.metric(rotulo, valor)
        _trimestral(tri)
        lim = ce.LIMITES.get(perfil_alavancagem, ce.LIMITES["Padrão"])
        g1, g2 = st.columns(2)
        with g1:
            _grafico_linha(ind, "Dívida líquida/EBITDA", "Dívida líquida / EBITDA (LTM)", ".2f",
                           [(lim["alavancagem"][0], "verde", "#1b7a3d"), (lim["alavancagem"][1], "amarelo", "#c9a227")])
        with g2:
            _grafico_linha(ind, "Cobertura de juros (EBITDA/juros)", "Cobertura de juros (EBITDA / juros)", ".1f",
                           [(lim["cobertura"][0], "verde", "#1b7a3d"), (lim["cobertura"][1], "amarelo", "#c9a227")])
        notas = [f"EBIT: {u['Fonte do EBIT']}" if u["Fonte do EBIT"] else "",
                 f"D&A: {u['Fonte da D&A']}" if isinstance(u["Fonte da D&A"], str) and u["Fonte da D&A"] else "",
                 f"juros: {u['Fonte dos juros']}" if isinstance(u["Fonte dos juros"], str) and u["Fonte dos juros"] else ""]
        if pd.notna(u["Data-base da dívida"]) and u["Data-base da dívida"] < u["Fim do período"]:
            notas.append(f"dívida da data-base {u['Data-base da dívida']:%d/%m/%Y} (a empresa só tagueia a dívida no 10-K)")
        st.caption("Como cada número foi montado — " + "; ".join(n for n in notas if n) + ".")
        mostrar = ind.drop(columns=["Fonte do EBIT", "Fonte da D&A", "Fonte dos juros", "Data-base da dívida", "Juros (LTM)"])
        for c in mostrar.columns:
            if c.endswith("(LTM)") or c in ("Caixa e aplicações", "Dívida bruta", "Dívida líquida", "Patrimônio líquido", "Ativo total"):
                mostrar[c] = mostrar[c] / BI
        config = {c: st.column_config.NumberColumn(c.replace("(LTM)", "(LTM, US$ bi)") if c.endswith("(LTM)") else c + " (US$ bi)", format="%.1f")
                  for c in mostrar.columns if c.endswith("(LTM)") or c in ("Caixa e aplicações", "Dívida bruta", "Dívida líquida", "Patrimônio líquido", "Ativo total")}
        config.update({
            "Fim do período": st.column_config.DateColumn("Período", format="DD/MM/YYYY"),
            "Margem EBITDA": st.column_config.NumberColumn(format="percent"),
            "Dívida líquida/EBITDA": st.column_config.NumberColumn(format="%.2fx"),
            "Dívida bruta/EBITDA": st.column_config.NumberColumn(format="%.2fx"),
            "Cobertura de juros (EBITDA/juros)": st.column_config.NumberColumn(format="%.1fx"),
            "Cobertura de juros (EBIT/juros)": st.column_config.NumberColumn(format="%.1fx"),
            "FCL/Dívida bruta": st.column_config.NumberColumn(format="percent"),
            "Liquidez corrente": st.column_config.NumberColumn(format="%.2fx"),
            "Dívida/(Dívida+PL)": st.column_config.NumberColumn(format="percent"),
        })
        with st.container(border=True):
            st.dataframe(mostrar, column_config=config, width="stretch", hide_index=True, placeholder="n/d")
    else:
        cards = [
            ("Ativo total", fmt(u["Ativo total"] / BI, "US$ {:,.0f} bi")),
            ("Patrimônio líquido", fmt(u["Patrimônio líquido"] / BI, "US$ {:,.1f} bi")),
            ("PL / Ativo", fmt(u["PL/Ativo"] * 100, "{:.1f}%")),
            ("ROE (LTM)", fmt(u["ROE (LTM, PL final)"] * 100, "{:.1f}%")),
            ("ROA (LTM)", fmt(u["ROA (LTM, ativo final)"] * 100, "{:.2f}%")),
            ("Índice de eficiência", fmt(u["Índice de eficiência"] * 100, "{:.0f}%")),
            ("Provisão/Receita", fmt(u["Provisão/Receita"] * 100, "{:.1f}%")),
            ("Lucro líquido (LTM)", fmt(u["Lucro líquido (LTM)"] / BI, "US$ {:,.1f} bi")),
        ]
        colunas = st.columns(4)
        for i, (rotulo, valor) in enumerate(cards):
            with colunas[i % 4], st.container(border=True):
                st.metric(rotulo, valor)
        _trimestral(tri)
        g1, g2 = st.columns(2)
        with g1:
            _grafico_linha(ind, "PL/Ativo", "Patrimônio líquido / Ativo", ".1%")
        with g2:
            _grafico_linha(ind, "ROE (LTM, PL final)", "ROE (LTM)", ".1%")
        mostrar = ind.copy()
        for c in ("Ativo total", "Patrimônio líquido", "Lucro líquido (LTM)", "Receita líquida (LTM)",
                  "Provisão p/ perdas (LTM)", "Despesas não-juros (LTM)", "Depósitos", "Dívida (LP + CP)"):
            mostrar[c] = mostrar[c] / BI
        config = {c: st.column_config.NumberColumn(c + " (US$ bi)", format="%.1f") for c in (
            "Ativo total", "Patrimônio líquido", "Lucro líquido (LTM)", "Receita líquida (LTM)",
            "Provisão p/ perdas (LTM)", "Despesas não-juros (LTM)", "Depósitos", "Dívida (LP + CP)")}
        config.update({"Fim do período": st.column_config.DateColumn("Período", format="DD/MM/YYYY")})
        for c in ("PL/Ativo", "ROE (LTM, PL final)", "ROA (LTM, ativo final)", "Índice de eficiência", "Provisão/Receita"):
            config[c] = st.column_config.NumberColumn(format="percent")
        config["Dívida/PL"] = st.column_config.NumberColumn(format="%.2fx")
        with st.container(border=True):
            st.dataframe(mostrar, column_config=config, width="stretch", hide_index=True, placeholder="n/d")


with aba_detalhe:
    emissores_analisaveis = [e for e in auto["Emissor"] if calculados.get(e)]
    escolha = st.selectbox("Emissor da base", emissores_analisaveis, key="ce_emissor") if emissores_analisaveis else None
    if escolha:
        m = auto[auto["Emissor"] == escolha].iloc[0]
        r = calculados[escolha]
        st.header(escolha)
        if m["Nota"]:
            st.info(m["Nota"])
        _detalhe(r[0], r[1], r[2], r[3], r[4], m["Perfil de alavancagem"], r[5])
        if escolha in cusips_por_emissor:
            st.markdown("###### Bonds na base")
            with st.container(border=True):
                st.dataframe(cusips_por_emissor[escolha], width="stretch", hide_index=True)

    with st.expander("Analisar outra empresa (busca por nome na SEC)"):
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
                    extra = _calcular(int(opcoes[nome_escolhido]))
                if extra is None:
                    st.warning("Sem fatos us-gaap pra essa empresa.")
                else:
                    st.subheader(nome_escolhido)
                    _detalhe(extra[0], extra[1], extra[2], extra[3], extra[4], "Padrão", extra[5])
