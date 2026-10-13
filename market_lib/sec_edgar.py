"""Demonstracoes DIVULGADAS por emissores dos EUA, lidas da API publica XBRL da SEC
(data.sec.gov) — o que as proprias empresas arquivam no 10-K (anual) e no 10-Q (trimestral).

Regra do modulo: NENHUM indicador e calculado. Cada celula e um fato XBRL exatamente como
arquivado, e cada coluna aponta pro arquivamento de origem (numero de acesso -> link no EDGAR),
pra qualquer pessoa conferir na SEC. So muda a unidade (dolares -> US$ milhoes) na exibicao.

Limites da fonte (confirmados contra dado real):
- 'companyfacts' so traz tags de taxonomias padrao (us-gaap). Linha com tag PROPRIA da empresa
  (extensao) nao vem — ex.: a divida da Ford, da Caterpillar e da T-Mobile. Fica 'n/a' aqui;
  o documento no link tem o numero.
- O 10-Q traz o resultado do trimestre (3 meses) e o acumulado do ano, mas a demonstracao de
  fluxo de caixa so sai acumulada. O 4o trimestre nao e arquivado isolado (so no earnings
  release). Por isso ha tres visoes: trimestre (3 meses), acumulado do ano e anual.
- Medidas nao-GAAP (EBITDA ajustado, divida liquida, segment operating income...) nao existem
  no XBRL: so no earnings release (8-K, item 2.02) — o modulo devolve os links dos ultimos.
- Divida: cada empresa a abre de um jeito, entao cada tag de divida e uma linha propria, sem somar.
"""

import os
import time

import pandas as pd
import requests
import streamlit as st

URL_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
URL_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
URL_INDICE = "https://www.sec.gov/Archives/edgar/data/{cik}/{semhifen}/{accn}-index.htm"
URL_EMPRESA = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}&type={tipo}&dateb=&owner=include&count=40"
PAUSA_ENTRE_CHAMADAS = 0.12  # a SEC pede <= 10 requisicoes/s

FLUXO, INSTANTE = "fluxo", "instante"

# (demonstracao, chave, rotulo, [tags us-gaap em ordem de prioridade], tipo). Pra cada linha vale UMA
# tag — a que cobre mais periodos — sem misturar tags entre colunas.
_DIVIDA = [
    ("DebtLongtermAndShorttermCombinedAmount", "Total debt (long- and short-term combined)"),
    ("DebtAndCapitalLeaseObligations", "Debt and finance lease obligations"),
    ("LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", "Long-term debt and finance leases, incl. current maturities"),
    ("LongTermDebt", "Long-term debt (incl. current portion)"),
    ("LongTermDebtNoncurrent", "Long-term debt, noncurrent"),
    ("LongTermDebtAndCapitalLeaseObligations", "Long-term debt and finance leases, noncurrent"),
    ("LongTermNotesPayable", "Long-term notes payable"),
    ("LongTermDebtCurrent", "Current portion of long-term debt"),
    ("LongTermDebtAndCapitalLeaseObligationsCurrent", "Current portion of long-term debt and finance leases"),
    ("DebtCurrent", "Short-term debt (current)"),
    ("ShortTermBorrowings", "Short-term borrowings"),
    ("NotesPayableCurrent", "Notes payable (current)"),
    ("CommercialPaper", "Commercial paper"),
]
_LINHAS_DIVIDA = [("Balance sheet", f"divida_{tag}", rotulo, [tag], INSTANTE) for tag, rotulo in _DIVIDA]

LINHAS_CORPORATIVA = [
    ("Income statement", "receita", "Revenue",
     ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
      "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet"], FLUXO),
    ("Income statement", "resultado_operacional", "Operating income (loss)", ["OperatingIncomeLoss"], FLUXO),
    ("Income statement", "juros", "Interest expense",
     ["InterestExpenseNonoperating", "InterestExpense", "InterestExpenseDebt", "InterestAndDebtExpense",
      "InterestExpenseLongTermDebt"], FLUXO),
    ("Income statement", "juros_liquidos", "Interest income (expense), net",
     ["InterestIncomeExpenseNonoperatingNet", "InterestIncomeExpenseNet"], FLUXO),
    ("Income statement", "lucro_antes_ir", "Income (loss) before income taxes",
     ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"], FLUXO),
    ("Income statement", "lucro_liquido", "Net income (loss) attributable to the company", ["NetIncomeLoss"], FLUXO),
    ("Income statement", "lucro_com_nci", "Net income (loss) incl. noncontrolling interests", ["ProfitLoss"], FLUXO),
    ("Cash flow statement", "da", "Depreciation and amortization",
     ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
      "DepreciationAmortizationAndAccretionNet", "DepreciationNonproduction"], FLUXO),
    ("Cash flow statement", "fco", "Net cash from operating activities",
     ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"], FLUXO),
    ("Cash flow statement", "capex", "Capital expenditures (payments for property, plant and equipment)",
     ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
      "PaymentsForCapitalImprovements"], FLUXO),
    ("Cash flow statement", "juros_pagos", "Interest paid (cash)", ["InterestPaidNet", "InterestPaid"], FLUXO),
    ("Balance sheet", "caixa", "Cash and cash equivalents", ["CashAndCashEquivalentsAtCarryingValue"], INSTANTE),
    ("Balance sheet", "aplicacoes", "Short-term investments / marketable securities",
     ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"], INSTANTE),
    ("Balance sheet", "ativo_circulante", "Total current assets", ["AssetsCurrent"], INSTANTE),
    ("Balance sheet", "ativo_total", "Total assets", ["Assets"], INSTANTE),
    ("Balance sheet", "passivo_circulante", "Total current liabilities", ["LiabilitiesCurrent"], INSTANTE),
    *_LINHAS_DIVIDA,
    ("Balance sheet", "passivo_total", "Total liabilities", ["Liabilities"], INSTANTE),
    ("Balance sheet", "patrimonio", "Total stockholders' equity", ["StockholdersEquity"], INSTANTE),
    ("Balance sheet", "patrimonio_nci", "Total equity incl. noncontrolling interests",
     ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], INSTANTE),
]

LINHAS_FINANCEIRA = [
    ("Income statement", "receita", "Net revenue (net of interest expense)", ["RevenuesNetOfInterestExpense", "Revenues"], FLUXO),
    ("Income statement", "juros", "Interest expense", ["InterestExpense", "InterestExpenseNonoperating"], FLUXO),
    ("Income statement", "provisao", "Provision for credit losses",
     ["ProvisionForCreditLosses", "ProvisionForLoanLeaseAndOtherLosses", "ProvisionForLoanAndLeaseLosses",
      "ProvisionForLoanLossesExpensed"], FLUXO),
    ("Income statement", "despesa_nao_juros", "Noninterest expense", ["NoninterestExpense"], FLUXO),
    ("Income statement", "lucro_antes_ir", "Income (loss) before income taxes",
     ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"], FLUXO),
    ("Income statement", "lucro_liquido", "Net income (loss) attributable to the company", ["NetIncomeLoss"], FLUXO),
    ("Income statement", "lucro_com_nci", "Net income (loss) incl. noncontrolling interests", ["ProfitLoss"], FLUXO),
    ("Cash flow statement", "fco", "Net cash from operating activities",
     ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"], FLUXO),
    ("Balance sheet", "caixa", "Cash and cash equivalents", ["CashAndCashEquivalentsAtCarryingValue"], INSTANTE),
    ("Balance sheet", "caixa_bancos", "Cash and due from banks", ["CashAndDueFromBanks"], INSTANTE),
    ("Balance sheet", "ativo_total", "Total assets", ["Assets"], INSTANTE),
    ("Balance sheet", "depositos", "Deposits", ["Deposits"], INSTANTE),
    *_LINHAS_DIVIDA,
    ("Balance sheet", "passivo_total", "Total liabilities", ["Liabilities"], INSTANTE),
    ("Balance sheet", "patrimonio", "Total stockholders' equity", ["StockholdersEquity"], INSTANTE),
    ("Balance sheet", "patrimonio_nci", "Total equity incl. noncontrolling interests",
     ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], INSTANTE),
]

# o 10-Q so publica fluxo de caixa acumulado no ano — nao ha "3 meses" (so no Q1, que e igual ao acumulado)
SO_ACUMULADO = {"fco", "capex", "juros_pagos"}

# visoes: (formulario do arquivamento, n de colunas, duracao minima/maxima em dias do fato de fluxo)
VISOES = {
    "trimestre": ("10-Q", 8, 80, 100),   # 3 meses
    "acumulado": ("10-Q", 6, 80, 290),   # acumulado do ano (3, 6 ou 9 meses): o mais longo
    "anual": ("10-K", 5, 350, 380),
}


def _user_agent():
    """A SEC exige um User-Agent identificando quem consulta. Configure SEC_USER_AGENT (variavel
    de ambiente ou .streamlit/secrets.toml) com 'Nome Empresa contato@dominio.com'."""
    valor = os.environ.get("SEC_USER_AGENT")
    if not valor:
        try:
            valor = st.secrets.get("SEC_USER_AGENT")
        except Exception:  # noqa: BLE001 — sem secrets.toml
            valor = None
    return valor or "SWM MFO Dash Offshore credit research"


def _get_json(url):
    time.sleep(PAUSA_ENTRE_CHAMADAS)
    resposta = requests.get(
        url, headers={"User-Agent": _user_agent(), "Accept-Encoding": "gzip, deflate"}, timeout=90
    )
    resposta.raise_for_status()
    return resposta.json()


def link_arquivamento(cik, accn):
    """Pagina do arquivamento no EDGAR (lista os documentos: 10-K/10-Q, anexos, planilha de dados)."""
    return URL_INDICE.format(cik=int(cik), semhifen=accn.replace("-", ""), accn=accn)


def link_empresa(cik, tipo="10-"):
    """Lista de arquivamentos da empresa no EDGAR (tipo '10-' = 10-K e 10-Q)."""
    return URL_EMPRESA.format(cik=int(cik), tipo=tipo)


def _eh_financeira(sic):
    try:
        sic = int(sic)
    except (TypeError, ValueError):
        return False
    return 6000 <= sic <= 6411 and sic != 6324


# ---------- perfil / arquivamentos ----------

def _buscar_perfil_bruto(cik):
    s = _get_json(URL_SUBMISSIONS.format(cik=int(cik)))
    r = s["filings"]["recent"]
    linhas = list(zip(r["form"], r["filingDate"], r["reportDate"], r["accessionNumber"], r["primaryDocument"], r["items"]))
    ultimos = [
        {"form": f, "filed": pd.Timestamp(d), "periodo": pd.Timestamp(rep) if rep else pd.NaT, "accn": a, "doc": doc}
        for f, d, rep, a, doc, _ in linhas if f in ("10-K", "10-Q", "20-F", "40-F")
    ][:4]
    periodicos = [pd.Timestamp(rep) for f, _, rep, _, _, _ in linhas if f in ("10-K", "10-Q") and rep]
    releases = [
        {"filed": pd.Timestamp(d), "accn": a, "doc": doc}
        for f, d, _, a, doc, itens in linhas if f == "8-K" and "2.02" in (itens or "").split(",")
    ][:4]
    return {
        "nome_sec": s.get("name"), "sic": s.get("sic"), "sic_descricao": s.get("sicDescription"),
        "tickers": s.get("tickers") or [], "fim_ano_fiscal": s.get("fiscalYearEnd"),
        "site": s.get("website") or s.get("investorWebsite") or "",
        "ultimos_arquivamentos": ultimos, "releases": releases,
        "ultimo_periodo_arquivado": max(periodicos) if periodicos else pd.NaT,
    }


def _arquivamentos(usgaap):
    """Cada 10-K/10-Q presente nos fatos: numero de acesso, formulario, data de arquivamento e
    periodo (a data de balanco mais recente do arquivamento, pois ele repete o ano anterior)."""
    registros = {}
    for tag in ("Assets", "LiabilitiesAndStockholdersEquity", "Liabilities"):
        for p in (usgaap.get(tag) or {}).get("units", {}).get("USD", []):
            if p.get("form") in ("10-K", "10-Q") and "start" not in p:
                fim = pd.Timestamp(p["end"])
                r = registros.setdefault(p["accn"], {"accn": p["accn"], "form": p["form"],
                                                      "filed": pd.Timestamp(p["filed"]), "periodo": fim})
                r["periodo"] = max(r["periodo"], fim)
        if registros:
            break
    if not registros:
        return pd.DataFrame(columns=["accn", "form", "filed", "periodo"])
    return pd.DataFrame(registros.values()).sort_values("periodo", ascending=False).reset_index(drop=True)


# ---------- tabelas ----------

def formatar_mm(v):
    """Dolares -> texto em US$ milhoes, negativos entre parenteses (como nos releases)."""
    if v is None or pd.isna(v):
        return "n/a"
    v = round(v / 1e6)
    return f"({abs(v):,.0f})" if v < 0 else f"{v:,.0f}"


def _montar_tabela(usgaap, filings, visao, linhas):
    """Tabela de uma visao: linhas = itens, colunas = arquivamentos (mais recente primeiro).
    So le fatos DO PROPRIO arquivamento (mesmo numero de acesso). Em cada linha, a tag de cada
    coluna e a 1a candidata com dado nele; a coluna "XBRL tag" lista as usadas. Devolve (DataFrame de texto,
    {chave: valor bruto da 1a coluna})."""
    _, _, dmin, dmax = VISOES[visao]
    accns = set(filings["accn"])
    cache = {}

    def pontos(tag):
        if tag not in cache:
            lista = (usgaap.get(tag) or {}).get("units", {}).get("USD") or []
            df = pd.DataFrame([p for p in lista if p["accn"] in accns])
            if not df.empty:
                df["end"] = pd.to_datetime(df["end"])
                if "start" in df:
                    df["start"] = pd.to_datetime(df["start"])
                    df["dias"] = (df["end"] - df["start"]).dt.days
                else:
                    df["start"], df["dias"] = pd.NaT, float("nan")
            cache[tag] = df
        return cache[tag]

    def valor(tag, f, tipo):
        df = pontos(tag)
        if df.empty:
            return None
        sub = df[(df["accn"] == f.accn) & (df["end"] == f.periodo)]
        if tipo == INSTANTE:
            sub = sub[sub["start"].isna()]
            return (float(sub.iloc[0]["val"]), None) if not sub.empty else None
        sub = sub[sub["start"].notna() & sub["dias"].between(dmin, dmax)]
        if sub.empty:
            return None
        linha = sub.sort_values("dias").iloc[-1]  # mais longo (acumulado); na visao de 3 meses so ha um
        return float(linha["val"]), int(linha["dias"])

    quadros = list(filings.itertuples())
    saida, brutos, dias_col = [], {}, [0] * len(quadros)
    for secao, chave, rotulo, tags, tipo in linhas:
        if visao == "trimestre" and chave in SO_ACUMULADO:
            continue
        vals, usadas = [], []
        for f in quadros:
            v = None
            for tag in tags:  # 1a tag com dado NAQUELE arquivamento (a empresa pode trocar de tag ao longo dos anos)
                v = valor(tag, f, tipo)
                if v is not None:
                    if tag not in usadas:
                        usadas.append(tag)
                    break
            vals.append(v)
        if not usadas:
            continue
        for i, v in enumerate(vals):
            if v is not None and v[1]:
                dias_col[i] = max(dias_col[i], v[1])
        brutos[chave] = vals[0][0] if vals and vals[0] is not None else None
        saida.append({"Statement": secao, "Line item": rotulo,
                      "XBRL tag": " / ".join(sorted(usadas, key=tags.index)),
                      "_valores": [None if v is None else v[0] for v in vals]})
    if visao == "acumulado":
        rotulos = [f"{round(d / 30.44)}M to {f.periodo:%b %d, %Y}" if d else f"{f.periodo:%b %d, %Y}"
                   for f, d in zip(quadros, dias_col)]
    else:
        rotulos = [f"{f.periodo:%b %d, %Y}" for f in quadros]
    linhas_txt = [{k: v for k, v in r.items() if k != "_valores"} | dict(zip(rotulos, map(formatar_mm, r["_valores"])))
                  for r in saida]
    return pd.DataFrame(linhas_txt), brutos


def _primeiro(brutos, *chaves):
    return next((brutos[c] for c in chaves if brutos.get(c) is not None), None)


def _tabelas_empresa(usgaap, arquivos, financeira):
    linhas = LINHAS_FINANCEIRA if financeira else LINHAS_CORPORATIVA
    tabelas, brutos, fontes = {}, {}, {}
    for visao, (form, n, _, _) in VISOES.items():
        filings = arquivos[arquivos["form"] == form].head(n).reset_index(drop=True)
        if filings.empty:
            tabelas[visao], brutos[visao], fontes[visao] = pd.DataFrame(), {}, pd.DataFrame()
            continue
        tabelas[visao], brutos[visao] = _montar_tabela(usgaap, filings, visao, linhas)
        fontes[visao] = filings
    return tabelas, brutos, fontes


def carregar_empresa_bruto(cik):
    """Tudo que a pagina precisa de uma empresa. Sem cache do Streamlit — seguro pra threads
    (ver `carregar_varios`)."""
    perfil = _buscar_perfil_bruto(cik)
    financeira = _eh_financeira(perfil["sic"])
    usgaap = _get_json(URL_FACTS.format(cik=int(cik)))["facts"].get("us-gaap", {})
    base = {"cik": int(cik), "perfil": perfil, "financeira": financeira}
    arquivos = _arquivamentos(usgaap) if usgaap else pd.DataFrame()
    if arquivos.empty:
        return {**base, "sem_us_gaap": True, "tabelas": {}, "fontes": {}, "resumo": None, "defasagem": None}
    tabelas, brutos, fontes = _tabelas_empresa(usgaap, arquivos, financeira)

    ultimo = arquivos.iloc[0]
    visao_resumo = "trimestre" if ultimo["form"] == "10-Q" else "anual"
    b = brutos.get(visao_resumo, {})
    resumo = {
        "form": ultimo["form"], "periodo": ultimo["periodo"], "accn": ultimo["accn"],
        "base": "3 months" if visao_resumo == "trimestre" else "Fiscal year",
        "receita": b.get("receita"),
        # se a empresa nao tagueia a linha principal, usa a equivalente do mesmo demonstrativo
        "lucro_liquido": _primeiro(b, "lucro_liquido", "lucro_com_nci"),
        "caixa": _primeiro(b, "caixa", "caixa_bancos"),
        "ativo_total": b.get("ativo_total"), "patrimonio": _primeiro(b, "patrimonio", "patrimonio_nci"),
    }
    # a API de fatos as vezes anda atras do ultimo arquivamento (ex.: Citigroup)
    defasagem = None
    arq = perfil["ultimo_periodo_arquivado"]
    if pd.notna(arq) and (arq - ultimo["periodo"]).days > 75:
        defasagem = (f"The SEC's XBRL data feed stops at {ultimo['periodo']:%b %d, %Y}, but a filing for "
                     f"{arq:%b %d, %Y} already exists — open the filings list to see the latest numbers.")
    return {**base, "sem_us_gaap": False, "tabelas": tabelas, "fontes": fontes, "resumo": resumo, "defasagem": defasagem}


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def buscar_perfil(cik):
    return _buscar_perfil_bruto(cik)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def carregar_empresa(cik):
    return carregar_empresa_bruto(cik)


def _carregar_um(cik):
    try:
        return cik, carregar_empresa_bruto(cik), None
    except Exception as erro:  # noqa: BLE001 — um emissor com erro nao pode derrubar os outros
        return cik, None, f"{type(erro).__name__}: {erro}"


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def carregar_varios(ciks):
    """ciks: tupla de CIKs. Baixa tudo em paralelo (4 threads — ~3 req/s, bem abaixo do limite de
    10/s da SEC). Devolve {cik: dados} e {cik: erro}."""
    from concurrent.futures import ThreadPoolExecutor

    resultados, erros = {}, {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for cik, resultado, erro in pool.map(_carregar_um, ciks):
            if erro:
                erros[cik] = erro
            else:
                resultados[cik] = resultado
    return resultados, erros


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def listar_registrantes():
    """Todos os registrantes (nome, CIK) que reportaram ativo total nos ultimos 4 trimestres JA
    ENCERRADOS, pela API de 'frames' da SEC — serve de busca por nome pra emissor fora do
    mapeamento, sem depender do www.sec.gov (que exige User-Agent com contato). Une 4
    trimestres porque cada 'frame' so traz quem fechou balanco naquele trimestre (empresas de
    ano fiscal atipico, como a Oracle, caem em outro), e o trimestre corrente ainda esta
    quase vazio — pedir so ele devolvia ~70 empresas."""
    ultimo_fechado = pd.Period(pd.Timestamp.today(), freq="Q") - 1
    partes = []
    for recuo in range(4):
        periodo = ultimo_fechado - recuo
        try:
            dados = _get_json(
                f"https://data.sec.gov/api/xbrl/frames/us-gaap/Assets/USD/CY{periodo.year}Q{periodo.quarter}I.json"
            )["data"]
        except requests.RequestException:
            continue
        partes.append(pd.DataFrame({"CIK": [e["cik"] for e in dados], "Nome": [e["entityName"] for e in dados]}))
    if not partes:
        return pd.DataFrame(columns=["CIK", "Nome"])
    return pd.concat(partes).drop_duplicates("CIK").reset_index(drop=True)
