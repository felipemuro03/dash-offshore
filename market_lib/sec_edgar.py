"""Metricas de credito de emissores dos EUA a partir da API publica XBRL da SEC
(data.sec.gov) — demonstracoes que as proprias empresas arquivam (10-K anual, 10-Q
trimestral), sem upload manual.

Limites da fonte (confirmados contra dado real, nao supostos):
- 'companyfacts' so traz tags de taxonomias padrao (us-gaap/ifrs/dei/srt). Tag PROPRIA da
  empresa (extensao) nao vem — ex.: a Ford nao tem nenhuma tag de divida la, a Caterpillar
  e a T-Mobile tambem nao, e a Oracle so tagueia a divida total no 10-K (anual). Nesses
  casos a metrica fica 'n/d' (ou usa o ultimo valor conhecido, sinalizado com a data-base)
  em vez de inventar.
- Fluxos (receita, EBITDA, caixa operacional...) so existem acumulados no ano (3m/6m/9m/12m);
  o 10-Q traz o YTD e o YTD do mesmo periodo do ano anterior, entao o fluxo e calculado em
  LTM (ultimos 12 meses): LTM = FY anterior + YTD atual - YTD do ano anterior.
- Uma empresa as vezes usa uma tag no 10-K e outra no 10-Q (AT&T, Broadcom, Dell...): o FY
  anterior pode vir de qualquer tag candidata do mesmo conceito, mas o YTD atual e o YTD
  anterior tem que vir da MESMA tag (senao a diferenca nao faz sentido).
- EBITDA nao e linha publicada: = resultado operacional + D&A (aproximacao de mercado). Quando
  a empresa nao apresenta resultado operacional (J&J, IBM, Nike...), usa lucro antes do IR +
  despesa de juros — sinalizado na coluna de fonte.
"""

import os
import time

import numpy as np
import pandas as pd
import requests
import streamlit as st

URL_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
URL_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FORMULARIOS_ANUAIS = {"10-K", "10-K/A", "10-KT"}
FORMULARIOS_PERIODICOS = FORMULARIOS_ANUAIS | {"10-Q", "10-Q/A"}
PAUSA_ENTRE_CHAMADAS = 0.12  # a SEC pede <= 10 requisicoes/s
TOL = pd.Timedelta(days=4)


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


# ---------- Candidatos de tag (ordem = prioridade) ----------

FLUXOS = {
    "receita": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                "SalesRevenueGoodsNet"],
    "resultado_operacional": ["OperatingIncomeLoss"],
    "lucro_antes_ir": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "lucro_liquido": ["NetIncomeLoss", "ProfitLoss"],
    "fco": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsForCapitalImprovements"],
}
# despesa de juros: primeiro as tags de despesa propriamente dita; depois proxies (sinalizados)
JUROS_DESPESA = ["InterestExpenseNonoperating", "InterestExpense", "InterestExpenseDebt",
                 "InterestAndDebtExpense", "InterestExpenseLongTermDebt"]
JUROS_LIQUIDOS = ["InterestIncomeExpenseNonoperatingNet", "InterestIncomeExpenseNet"]  # negativo = despesa liquida
JUROS_PAGOS = ["InterestPaidNet"]
DEPRECIACAO_TOTAL = ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                     "DepreciationAmortizationAndAccretionNet", "DepreciationNonproduction"]
DEPRECIACAO_PARTES = ["Depreciation", "AmortizationOfIntangibleAssets"]

FLUXOS_FINANCEIRA = {
    "receita_liquida": ["RevenuesNetOfInterestExpense", "Revenues"],
    "provisao": ["ProvisionForCreditLosses", "ProvisionForLoanLeaseAndOtherLosses",
                 "ProvisionForLoanAndLeaseLosses", "ProvisionForLoanLossesExpensed"],
    "despesa_nao_juros": ["NoninterestExpense"],
}

INSTANTES = {
    "caixa": ["CashAndCashEquivalentsAtCarryingValue"],
    "aplicacoes_cp": ["ShortTermInvestments", "MarketableSecuritiesCurrent",
                      "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "patrimonio_liquido": ["StockholdersEquity",
                           "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "ativo_total": ["Assets"],
    "ativo_circulante": ["AssetsCurrent"],
    "passivo_circulante": ["LiabilitiesCurrent"],
    "depositos": ["Deposits"],
    "div_combinada": ["DebtLongtermAndShorttermCombinedAmount"],
    "div_total_com_leasing": ["LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"],
    "div_lp_total": ["LongTermDebt"],
    "div_lp_nao_circ": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations",
                        "LongTermNotesPayable"],
    "div_lp_circ": ["LongTermDebtCurrent"],
    "div_circ": ["DebtCurrent"],
    "div_cp_emprest": ["ShortTermBorrowings"],
    "div_cp_papel": ["CommercialPaper"],
}


class _Fatos:
    """Fatos XBRL (us-gaap) de uma empresa com acesso memoizado a tabelas por tag."""

    def __init__(self, fatos_usgaap):
        self.fatos = fatos_usgaap
        self._cache = {}
        self.fins_ano_fiscal = self._calcular_fins_ano_fiscal()

    def tabela(self, tag, instante):
        chave = (tag, instante)
        if chave not in self._cache:
            self._cache[chave] = self._montar(tag, instante)
        return self._cache[chave]

    def _lista(self, tag):
        d = self.fatos.get(tag)
        if not d:
            return None
        u = d["units"]
        return u.get("USD") or u.get("pure") or next(iter(u.values()))

    def _montar(self, tag, instante):
        lista = self._lista(tag)
        if not lista:
            return None
        df = pd.DataFrame(lista)
        df = df[df["form"].isin(FORMULARIOS_PERIODICOS)].copy()
        if df.empty:
            return None
        df["end"] = pd.to_datetime(df["end"])
        df["filed"] = pd.to_datetime(df["filed"])
        if instante:
            if "start" in df:
                df = df[df["start"].isna()]
            chave = ["end"]
        else:
            if "start" not in df:
                return None
            df = df.dropna(subset=["start"]).copy()
            df["start"] = pd.to_datetime(df["start"])
            df["dias"] = (df["end"] - df["start"]).dt.days
            chave = ["start", "end"]
        if df.empty:
            return None
        # mesmo periodo reapresentado em arquivamentos posteriores: vale o mais recente
        return df.sort_values("filed").drop_duplicates(chave, keep="last").reset_index(drop=True)

    def _calcular_fins_ano_fiscal(self):
        """Datas de fim de ano fiscal = datas de balanco reportadas em qualquer 10-K. Usa os
        fatos BRUTOS (antes de deduplicar por data): senao o comparativo do 10-Q seguinte
        sobrescreve a linha do 10-K e o fim do ano fiscal some."""
        fins = set()
        for tag in ("Assets", "Liabilities", "StockholdersEquity", "LiabilitiesAndStockholdersEquity"):
            lista = self._lista(tag)
            if lista:
                fins.update(pd.Timestamp(e["end"]) for e in lista if e["form"] in FORMULARIOS_ANUAIS and "start" not in e)
        return sorted(fins)

    def periodos(self, n):
        ativos = self.tabela("Assets", True)
        if ativos is None:
            return []
        fins = []
        for fim in sorted(ativos["end"].unique(), reverse=True):
            fim = pd.Timestamp(fim)
            if not fins or (fins[-1] - fim) > pd.Timedelta(days=20):
                fins.append(fim)
        return fins[:n]


def _valor_ytd(df, fim, inicio_ano, dur_min=70, dur_max=300):
    achados = df[((df["end"] - fim).abs() <= TOL) & ((df["start"] - inicio_ano).abs() <= pd.Timedelta(days=8))
                 & df["dias"].between(dur_min, dur_max)]
    if achados.empty:
        return None
    linha = achados.sort_values("dias").iloc[-1]
    return float(linha["val"]), int(linha["dias"])


def _fy_de_qualquer_tag(tabelas, fy_fim):
    for df in tabelas:
        anuais = df[df["dias"].between(350, 380) & ((df["end"] - fy_fim).abs() <= TOL)]
        if not anuais.empty:
            return float(anuais["val"].iloc[-1])
    return None


def ltm(fatos, tags, fim):
    """Valor LTM de um fluxo em `fim`, tentando as tags em ordem. Retorna (valor, tag_usada)."""
    tabelas = [t for t in (fatos.tabela(tag, False) for tag in tags) if t is not None]
    fy_ends = fatos.fins_ano_fiscal
    # periodo que fecha exatamente um ano fiscal: o proprio valor anual
    for tag in tags:
        df = fatos.tabela(tag, False)
        if df is None:
            continue
        anuais = df[df["dias"].between(350, 380) & ((df["end"] - fim).abs() <= TOL)]
        if not anuais.empty:
            return float(anuais["val"].iloc[-1]), tag
    anteriores = [d for d in fy_ends if d < fim - pd.Timedelta(days=20)]
    if not anteriores:
        return np.nan, None
    fy_ant = max(anteriores)
    inicio_ano = fy_ant + pd.Timedelta(days=1)
    um_ano = pd.Timedelta(days=365)
    for tag in tags:
        df = fatos.tabela(tag, False)
        if df is None:
            continue
        atual = _valor_ytd(df, fim, inicio_ano)
        if atual is None:
            continue
        ytd, dur = atual
        anterior = df[((df["end"] - (fim - um_ano)).abs() <= pd.Timedelta(days=10))
                      & ((df["start"] - (inicio_ano - um_ano)).abs() <= pd.Timedelta(days=12))
                      & ((df["dias"] - dur).abs() <= 12)]
        if anterior.empty:
            continue
        fy_valor = _fy_de_qualquer_tag(tabelas, fy_ant)
        if fy_valor is None:
            continue
        return fy_valor + ytd - float(anterior["val"].iloc[-1]), tag
    return np.nan, None


def instante(fatos, tags, fim, defasagem_dias=0):
    """Foto de balanco em `fim` (1o candidato com dado); devolve (valor, data_base)."""
    for tag in tags:
        df = fatos.tabela(tag, True)
        if df is None:
            continue
        exato = df[(df["end"] - fim).abs() <= pd.Timedelta(days=3)]
        if not exato.empty:
            return float(exato.iloc[-1]["val"]), exato.iloc[-1]["end"]
        if defasagem_dias:
            antigos = df[(df["end"] < fim) & (df["end"] >= fim - pd.Timedelta(days=defasagem_dias))]
            if not antigos.empty:
                linha = antigos.sort_values("end").iloc[-1]
                return float(linha["val"]), linha["end"]
    return np.nan, pd.NaT


def _soma_parcial(*valores):
    return sum(0 if pd.isna(x) else x for x in valores)


def _divida_em(fatos, fim):
    """Divida financeira bruta no periodo `fim` (so valores desse mesmo dia, sem misturar
    datas). Regras em ordem — a 1a que fechar vale; devolve (valor, regra)."""
    def v(chave):
        return instante(fatos, INSTANTES[chave], fim)[0]

    combinada = v("div_combinada")
    if pd.notna(combinada):
        return combinada, "total combinado (CP+LP)"
    com_leasing = v("div_total_com_leasing")
    if pd.notna(com_leasing):
        return com_leasing + _soma_parcial(v("div_cp_emprest"), v("div_cp_papel")), "LP+leasing c/ vencimentos + CP"
    nao_circ = v("div_lp_nao_circ")
    if pd.notna(nao_circ):
        circ = v("div_circ")
        if pd.isna(circ):
            circ = _soma_parcial(v("div_lp_circ"), v("div_cp_emprest"), v("div_cp_papel"))
        return nao_circ + circ, "LP nao circulante + circulante"
    lp_total = v("div_lp_total")
    if pd.notna(lp_total):
        return lp_total + _soma_parcial(v("div_cp_emprest"), v("div_cp_papel")), "LP total + CP"
    return np.nan, None


def _divida_com_defasagem(fatos, fim, datas, max_dias=130):
    """Divida no periodo; se nao existe nele (ex.: Oracle so tagueia divida no 10-K), usa a mais
    recente de um periodo anterior (ate max_dias antes) e devolve a data-base — nunca mistura
    componentes de datas diferentes."""
    valor, regra = _divida_em(fatos, fim)
    if pd.notna(valor):
        return valor, fim, regra
    for data in sorted((d for d in datas if fim - pd.Timedelta(days=max_dias) <= d < fim), reverse=True):
        valor, regra = _divida_em(fatos, data)
        if pd.notna(valor):
            return valor, data, regra
    return np.nan, pd.NaT, None


def _juros(fatos, fim):
    """Despesa de juros LTM e de onde veio: despesa propriamente dita > juros liquidos
    (receita-despesa; so conta se for despesa liquida) > juros pagos em caixa."""
    valor, tag = ltm(fatos, JUROS_DESPESA, fim)
    if pd.notna(valor) and valor > 0:
        return valor, "despesa de juros"
    valor, tag = ltm(fatos, JUROS_LIQUIDOS, fim)
    if pd.notna(valor) and valor < 0:
        return -valor, "juros líquidos (despesa − receita)"
    valor, tag = ltm(fatos, JUROS_PAGOS, fim)
    if pd.notna(valor) and valor > 0:
        return valor, "juros pagos (caixa)"
    return np.nan, None


def _depreciacao(fatos, fim):
    valor, _ = ltm(fatos, DEPRECIACAO_TOTAL, fim)
    if pd.notna(valor):
        return valor, "D&A total"
    dep, _ = ltm(fatos, ["Depreciation"], fim)
    amort, _ = ltm(fatos, ["AmortizationOfIntangibleAssets"], fim)
    if pd.notna(dep) and pd.notna(amort):
        return dep + amort, "depreciação + amortização de intangíveis"
    if pd.notna(dep):
        return dep, "só depreciação (sem amortização de intangíveis)"
    return np.nan, None


def _eh_financeira(sic):
    try:
        sic = int(sic)
    except (TypeError, ValueError):
        return False
    return 6000 <= sic <= 6411 and sic != 6324


def _buscar_perfil_bruto(cik):
    s = _get_json(URL_SUBMISSIONS.format(cik=int(cik)))
    recentes = s["filings"]["recent"]
    ultimos = [
        (f, d, r) for f, d, r in zip(recentes["form"], recentes["filingDate"], recentes["reportDate"])
        if f in ("10-K", "10-Q", "20-F", "40-F")
    ][:4]
    periodicos = [
        (f, d, r) for f, d, r in zip(recentes["form"], recentes["filingDate"], recentes["reportDate"])
        if f in ("10-K", "10-Q") and r
    ]
    return {
        "ultimo_periodo_arquivado": pd.Timestamp(max(r for _, _, r in periodicos)) if periodicos else pd.NaT,
        "nome_sec": s.get("name"), "sic": s.get("sic"), "sic_descricao": s.get("sicDescription"),
        "tickers": s.get("tickers") or [], "fim_ano_fiscal": s.get("fiscalYearEnd"),
        "categoria": s.get("category"), "ultimos_arquivamentos": ultimos,
    }


def calcular_metricas_bruto(cik, financeira=None, n_periodos=10):
    """Metricas brutas por periodo (mais recente primeiro) a partir dos fatos XBRL da SEC.
    Devolve (DataFrame, perfil). financeira=None decide pelo SIC da empresa. Sem cache do
    Streamlit — seguro pra chamar de varias threads (ver `carregar_varios`)."""
    perfil = _buscar_perfil_bruto(cik)
    if financeira is None:
        financeira = _eh_financeira(perfil["sic"])
    bruto = _get_json(URL_FACTS.format(cik=int(cik)))["facts"].get("us-gaap", {})
    if not bruto:
        return pd.DataFrame(), {**perfil, "financeira": financeira, "sem_us_gaap": True}
    fatos = _Fatos(bruto)
    datas = fatos.periodos(60)

    linhas = []
    for fim in fatos.periodos(n_periodos):
        r = {"Fim do período": fim}
        if financeira:
            for nome, tags in FLUXOS_FINANCEIRA.items():
                r[nome], _ = ltm(fatos, tags, fim)
            r["lucro_liquido"], _ = ltm(fatos, FLUXOS["lucro_liquido"], fim)
            for chave in ("ativo_total", "patrimonio_liquido", "depositos"):
                r[chave], _ = instante(fatos, INSTANTES[chave], fim)
            r["divida_bruta"], r["regra_divida"] = _divida_em(fatos, fim)
        else:
            for nome, tags in FLUXOS.items():
                r[nome], _ = ltm(fatos, tags, fim)
            r["juros"], r["juros_fonte"] = _juros(fatos, fim)
            r["juros_liquidos_sinal"], _ = ltm(fatos, JUROS_LIQUIDOS, fim)
            r["depreciacao"], r["depreciacao_fonte"] = _depreciacao(fatos, fim)
            for chave in ("caixa", "aplicacoes_cp", "patrimonio_liquido", "ativo_total", "ativo_circulante",
                          "passivo_circulante"):
                r[chave], _ = instante(fatos, INSTANTES[chave], fim)
            r["divida_bruta"], r["divida_data_base"], r["regra_divida"] = _divida_com_defasagem(fatos, fim, datas)
        linhas.append(r)

    return pd.DataFrame(linhas), {**perfil, "financeira": financeira, "sem_us_gaap": False}


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def buscar_perfil(cik):
    return _buscar_perfil_bruto(cik)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def calcular_metricas(cik, financeira=None, n_periodos=10):
    return calcular_metricas_bruto(cik, financeira, n_periodos)


def _carregar_um(item):
    cik, financeira = item
    try:
        return cik, calcular_metricas_bruto(cik, financeira), None
    except Exception as erro:  # noqa: BLE001 — um emissor com erro nao pode derrubar os outros
        return cik, None, f"{type(erro).__name__}: {erro}"


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def carregar_varios(itens):
    """itens: tupla de (cik, financeira|None). Baixa tudo em paralelo (4 threads — ~3 req/s,
    bem abaixo do limite de 10/s da SEC). Devolve {cik: (df, perfil)} e {cik: erro}."""
    from concurrent.futures import ThreadPoolExecutor

    resultados, erros = {}, {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for cik, resultado, erro in pool.map(_carregar_um, itens):
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
