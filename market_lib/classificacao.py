"""Classificacao de ativos offshore por classe (Equities US/Global/EM, Investment Grade
por prazo, High Yield, Emerging Markets, Money Markets, Inflation, Hybrids, Gold, Crypto,
Alternatives) — usada pela pagina de Posicoes Consolidadas.

Duas camadas:
1. Classificador automatico por regras (rating de emissor pesquisado manualmente, prazo
   ate o vencimento, palavras-chave na descricao).
2. Tabela de classificacao manual (CSV editavel na tela) que sempre tem prioridade sobre
   o automatico — mesmo padrao do classificacao.csv usado no Dash Onshore.
"""

import datetime as dt
import re
from pathlib import Path

import pandas as pd

CLASSES = [
    "Equities US",
    "Equities Global",
    "Equities EM",
    "Money Markets",
    "Inflation",
    "Investment Grade - Short Term",
    "Investment Grade - Mid Term",
    "Investment Grade - Long Term",
    "High Yield",
    "Emerging Markets",
    "Hybrids",
    "Gold",
    "Crypto",
    "Alternatives",
]

# ---------- Rating de emissores de Renda Fixa (pesquisado em 2026-08-26 via S&P/Moody's/
# Fitch) — "Emerging Markets" aqui sobrepoe IG/HY pra qualquer emissor de pais emergente,
# por instrucao explicita do usuario ("tudo que for relacionado a Brasil, e o Pemex
# tambem, e Emerging Markets"), independente do rating de credito especifico.
# Formato: chave = trecho da descricao/ticker (maiusculo), valor = (classe, nota).
_RATING_EMISSOR_HY = {
    "VIACOMCBS": "Paramount/ViacomCBS — S&P BB+ (junk), CreditWatch negativo",
    "CHTR": "Charter Communications — Moody's Ba2 / S&P BB+",
    "BBWI": "Bath & Body Works — Moody's Ba2 / S&P BB+",
    "CZR": "Caesars Entertainment — S&P B+",
    "GT ": "Goodyear Tire — S&P B+ / Moody's B1",
}

_RATING_EMISSOR_EM = {
    # Brasil
    "BRAZIL": "Brasil soberano — S&P/Fitch BB, Moody's Ba1",
    "CD ITAU": "Itau Unibanco — rating internacional travado pelo teto soberano do Brasil",
    "SUZANO": "Suzano — BBB-/Baa3 (IG no limite, mas emissor brasileiro)",
    "MRFGBZ": "Marfrig — Fitch BB+",
    "VALEBZ": "Vale — BBB/Baa2 (IG no limite, mas emissor brasileiro)",
    "LIGTBZ": "Light S.A. — Fitch B- (saiu de default recente)",
    "BANCO BTG PACTUAL": "BTG Pactual (Cayman) — Moody's Ba1/S&P BB+, banco brasileiro",
    # Mexico
    "PEMEX": "Petroleos Mexicanos — Moody's B1/Fitch BB+ (anjo caido)",
    "BBVA MEXICO": "BBVA Mexico — subsidiaria mexicana",
}

_RATING_EMISSOR_IG = {
    "MERRILL LYNCH": "Sucessora Bank of America — S&P A-/Moody's A1",
    "BANK AMER": "Bank of America — S&P A-/Moody's A1",
    "CITIGROUP": "Citigroup — S&P BBB+/Moody's A3",
    "CATERPILLAR": "Caterpillar — S&P A/Moody's A2",
    "CAPITAL ONE": "Capital One — Moody's Baa1/S&P BBB",
    "CROWDSTRIKE": "CrowdStrike — Moody's Baa2/S&P BBB-",
    "DEERE JOHN": "John Deere Capital — S&P A/Moody's A2",
    "DELL INTL": "Dell Technologies — S&P BBB/BBB+",
    "GENERAL DYNAMICS": "General Dynamics — S&P A/Moody's A2",
    "GENERAL MTRS FINL": "GM Financial — Moody's Baa2/S&P BBB",
    "ALPHABET": "Alphabet — Moody's Aa2/S&P AA+",
    "HCA INC": "HCA — Moody's Baa3/S&P BBB",
    "INTERNATIONAL BUSINESS MACHS": "IBM — Moody's A3/S&P A-",
    "JPMORGAN": "JPMorgan Chase — S&P A/Moody's Aa2",
    "METLIFE": "MetLife — Moody's A3",
    "MORGAN STANLEY": "Morgan Stanley — S&P A-/Moody's A1",
    "ARCELORMITTAL": "ArcelorMittal — Moody's Baa2/S&P BBB",
    "MICRON": "Micron — S&P BBB/Moody's Baa2",
    "NXP": "NXP Semiconductors — S&P BBB+/Moody's Baa3",
    "ORACLE": "Oracle — S&P BBB- (limite)/Moody's Baa2",
    "PACIFIC GAS": "PG&E — Moody's Baa3 (opco)",
    "SANTANDER HLDGS": "Santander Holdings USA — S&P BBB+/Moody's Baa2",
    "TEACHERS INSURANCE": "TIAA — S&P AA+/Moody's Aa1",
    "T-MOBILE": "T-Mobile USA — Moody's Baa1/S&P BBB+",
    "UBS GROUP": "UBS — Moody's A3",
    "UNITEDHEALTH": "UnitedHealth — S&P A+",
    "RTX ": "RTX Corp — S&P BBB+/Moody's Baa1",
    "UNITED TECHNOLOGIES": "RTX Corp (nome anterior) — S&P BBB+/Moody's Baa1",
    "GOLDMAN SACHS": "Goldman Sachs — S&P BBB+/Moody's A2",
    " GS ": "Goldman Sachs — S&P BBB+/Moody's A2",
    "JOHNSON & JOHNSON": "J&J — S&P AAA",
    "CVS": "CVS Health — S&P BBB",
    "NIKE": "Nike — Moody's A2/S&P A+",
    "AMERICAN EXPRESS": "American Express — S&P BBB+/Moody's A2",
    "AXP": "American Express — S&P BBB+/Moody's A2",
    "NEXTERA": "NextEra Energy — Moody's Baa1/S&P A-",
    " NEE ": "NextEra Energy — Moody's Baa1/S&P A-",
    "BROADCOM": "Broadcom — Moody's A3/S&P A-",
    "AVGO": "Broadcom — Moody's A3/S&P A-",
    "WELLS FARGO": "Wells Fargo — Moody's A1/S&P BBB+",
    "WFC": "Wells Fargo — Moody's A1/S&P BBB+",
    "UNITED STATES TREAS": "Tesouro americano — S&P/Fitch AA+, Moody's Aa1",
    "FORD MOTOR": "Ford — S&P/Fitch BBB- (IG no limite), Moody's Ba1 (HY) — rating dividido, maioria diz IG",
    " F ": "Ford — S&P/Fitch BBB- (IG no limite), Moody's Ba1 (HY) — rating dividido, maioria diz IG",
    "OCCIDENTAL": "Occidental Petroleum — Moody's Baa3/Fitch BBB (IG), S&P BB+ (HY) — rating dividido, maioria diz IG",
    "OXY": "Occidental Petroleum — Moody's Baa3/Fitch BBB (IG), S&P BB+ (HY) — rating dividido, maioria diz IG",
    "JNJ": "J&J — S&P AAA",
    "NKE": "Nike — Moody's A2/S&P A+",
    " C ": "Citigroup — S&P BBB+/Moody's A3",
    "AT&T": "AT&T — S&P BBB/Moody's Baa2",
    " T ": "AT&T — S&P BBB/Moody's Baa2",
    "JPM ": "JPMorgan Chase — S&P A/Moody's Aa2",
}

_HYBRIDS = {"LSERIES DAC"}

# ---------- ETFs da Avenue: a planilha 'Data' so tem o ticker (sem nome descritivo),
# entao esses precisam de um dicionario proprio em vez de casar palavra-chave. ----------
_TICKERS_ETF_AVENUE = {
    "SPTL": "Investment Grade - Long Term",
    "SPIB": "Investment Grade - Mid Term",
    "SPHY": "High Yield",
    "IWM": "Equities US",
    "SPY": "Equities US",
    "QQQI": "Equities US",
    "VTIP": "Inflation",
    "QQQ": "Equities US",
    "VT": "Equities Global",
    "TLT": "Investment Grade - Long Term",
    "IGIB": "Investment Grade - Mid Term",
    "ARTY": "Equities US",
    "SHY": "Investment Grade - Short Term",
    "IWMI": "Equities US",
    "GDX": "Gold",
    "IEF": "Investment Grade - Mid Term",
    "XLE": "Equities US",
    "ITA": "Equities US",
    "IGSB": "Investment Grade - Short Term",
    "EMB": "Emerging Markets",
    "BOTZ": "Equities Global",
    "SPSB": "Investment Grade - Short Term",
    "EEM": "Equities EM",
    "ROBT": "Equities Global",
    "TMF": "Investment Grade - Long Term",
    "IXJ": "Equities Global",
    "BITO": "Crypto",
    "SOXX": "Equities US",
    "IBIT": "Crypto",
    "SLYV": "Equities US",
    "VWO": "Equities EM",
    "FLOT": "Money Markets",
    "AGG": "Investment Grade - Mid Term",
    "IBDW": "Investment Grade - Mid Term",
    "IBDV": "Investment Grade - Mid Term",
    "IBDX": "Investment Grade - Mid Term",
    "IBDR": "Investment Grade - Mid Term",
    "IBDS": "Investment Grade - Mid Term",
    "IBDU": "Investment Grade - Mid Term",
    "IBTI": "Investment Grade - Mid Term",
    "TFLO": "Money Markets",
    "USFR": "Money Markets",
    "ACWI": "Equities Global",
    "AOM": "Alternatives",
}

# ---------- Acoes individuais (Stocks/Equities) — a maioria e US, essas sao as excecoes
# conhecidas por nacionalidade/domicilio da empresa. ----------
_EQUITY_EM = {"TSM", "NU"}  # Taiwan Semiconductor, Nu Holdings (Brasil)
_EQUITY_GLOBAL = {"CAMECO", "EQX", "VINTY"}  # mineradoras canadenses / holding luxemburguesa

# ---------- Fundos/ETFs com nome descritivo (BTG Investment Funds, Avenue Funds/UCITs) —
# classificacao por palavra-chave no nome. ----------
_PALAVRAS_RENDA_FIXA = (
    "BOND", "CORP BD", "CORPORATE BD", "FIXED INCOME", "INCOME FUND", "CREDIT", "CORPORATE",
)
_PALAVRAS_EM = ("EMERGING MARKET", "EMERGING MKT")
_PALAVRAS_HIGH_YIELD = ("HIGH YIELD", "HIGH INCOME")
_PALAVRAS_INFLACAO = ("INFLATION",)
_PALAVRAS_GOLD = ("GOLD",)
_PALAVRAS_REAL_ESTATE = ("REAL ESTATE",)
_PALAVRAS_EQUITY_GLOBAL = ("GLOBAL", "WORLD", "INTERNATIONAL", "INTL", "EUROPE", "BRANDS")
_PALAVRAS_EQUITY_US = (
    "S&P 500", "RUSSELL", "NASDAQ", "AEROSPACE", "HEALTHCARE", "TECHNOLOGY",
    "SEMICONDUCTOR", "URANIUM", "U.S.", "US GROWTH", "US EQUITY", "AMERICAN GROWTH",
)


def _classificar_fundo_por_nome(descricao_norm):
    eh_renda_fixa = any(p in descricao_norm for p in _PALAVRAS_RENDA_FIXA)

    if any(p in descricao_norm for p in _PALAVRAS_EM):
        return ("Emerging Markets" if eh_renda_fixa else "Equities EM"), "alta"
    if any(p in descricao_norm for p in _PALAVRAS_HIGH_YIELD):
        return "High Yield", "alta"
    if any(p in descricao_norm for p in _PALAVRAS_INFLACAO):
        return "Inflation", "alta"
    if any(p in descricao_norm for p in _PALAVRAS_GOLD) and "GOLDMAN" not in descricao_norm:
        return "Gold", "alta"
    if any(p in descricao_norm for p in _PALAVRAS_REAL_ESTATE):
        return "Alternatives", "baixa"
    if re.search(r"\bTREAS\b|\bTIPS\b", descricao_norm) or "INVT GRADE CORP" in descricao_norm:
        return "Investment Grade - Mid Term", "alta"
    if eh_renda_fixa:
        return "Investment Grade - Mid Term", "baixa"
    if any(p in descricao_norm for p in _PALAVRAS_EQUITY_GLOBAL):
        return "Equities Global", "alta"
    if any(p in descricao_norm for p in _PALAVRAS_EQUITY_US):
        return "Equities US", "alta"
    return "Equities US", "baixa"

# ---------- Money Markets: lista explicita dada pelo usuario ----------
# Os 4 "Balance" da Avenue (saldo na conta banking, nao e posicao de investimento) nao
# entram aqui — sao descartados por completo em carregar_avenue_data, nunca chegam ate o
# classificador.
_MONEY_MARKETS_NOMES = {
    "FEDERATED HERMES SHORT TERM DAILY U S DOLLAR FUND RET SHARES",
    "EURO CURRENCY",
    "PICTET SHORT-TERM MONEY MARKET FUND CLASS R (EUR) ISIN LU0128495834",
    "U.S.DOLLARS CURRENCY",
    "FRANKLIN U.S. DOLLAR S/T MMF A(ACC)USD",
    "BGF US DOLLAR RESERVE A2 USD",
    "FTGF WA US GOVT LQDTY A $ ACC",
    "JPM USD STANDARD MNY MKT VNAV A (ACC.)",
    "FLOT",
}

_PADRAO_DATA = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")


def normalizar_chave(texto):
    return re.sub(r"\s+", " ", str(texto or "").strip().upper())


def _bucket_prazo_ig(anos):
    if anos is None:
        return "Investment Grade - Mid Term"
    if anos <= 3:
        return "Investment Grade - Short Term"
    if anos <= 10:
        return "Investment Grade - Mid Term"
    return "Investment Grade - Long Term"


def _anos_ate_vencimento(maturity_date, referencia=None):
    if maturity_date is None or pd.isna(maturity_date):
        return None
    referencia = referencia or dt.date.today()
    if hasattr(maturity_date, "date"):
        maturity_date = maturity_date.date()
    return (maturity_date - referencia).days / 365.25


def _maturidade_da_descricao(descricao):
    """Bonds da Avenue tem a data de vencimento embutida no nome (ultima data no texto,
    formato DD/MM/AA), ex.: 'BRAZIL 5.625 21/02/47' -> vencimento 21/02/2047."""
    matches = _PADRAO_DATA.findall(descricao)
    if not matches:
        return None
    dia, mes, ano = matches[-1]
    ano = int(ano)
    if ano < 100:
        ano += 2000
    try:
        return dt.date(ano, int(mes), int(dia))
    except ValueError:
        return None


def _classificar_rating_emissor(descricao_norm):
    for chave, nota in _RATING_EMISSOR_EM.items():
        if chave in descricao_norm:
            return "Emerging Markets", nota
    for chave, nota in _RATING_EMISSOR_HY.items():
        if chave in descricao_norm:
            return "High Yield", nota
    for chave, nota in _RATING_EMISSOR_IG.items():
        if chave in descricao_norm:
            return "Investment Grade", nota
    return None, None


def _eh_money_market(descricao_norm):
    if descricao_norm in _MONEY_MARKETS_NOMES:
        return True
    if re.search(r"\bMONEY MARKET\b|\bMNY MKT\b|\bMMF\b", descricao_norm):
        return True
    return False


def classificar_automatico(descricao, categoria_origem, maturity_date=None):
    """Retorna (classe, confianca, nota) — confianca 'alta' quando bate uma regra
    especifica (rating pesquisado, lista de money market, palavra-chave clara),
    'baixa' quando cai no fallback generico (precisa revisao manual)."""
    descricao_norm = normalizar_chave(descricao)
    categoria_norm = normalizar_chave(categoria_origem)

    if any(h in descricao_norm for h in _HYBRIDS):
        return "Hybrids", "alta", "Fundo proprio (gestao interna, multi-ativos)"

    if _eh_money_market(descricao_norm):
        return "Money Markets", "alta", "Lista de liquidez / saldo em conta"

    if "DIGITAL ASSET" in categoria_norm or re.search(r"\bUSDC\b|\bBTC\b|\bBITCOIN\b|\bETHEREUM\b", descricao_norm):
        return "Crypto", "alta", "Ativo digital"

    if "ALTERNATIVE INVESTMENT" in categoria_norm or "LIMITED PARTNERSHIP" in categoria_norm:
        return "Alternatives", "alta", "Fundo alternativo / private"

    if re.search(r"\bGOLD\b", descricao_norm) and "GOLDMAN" not in descricao_norm:
        return "Gold", "alta", "Exposicao a ouro"

    eh_renda_fixa = (
        "FIXED INCOME" in categoria_norm or "BOND" == categoria_norm.strip()
        or categoria_norm.strip() == "BONDS"
    )
    if eh_renda_fixa:
        if re.search(r"\bTIPS\b|INFLATION PROTECTED", descricao_norm):
            return "Inflation", "alta", "Titulo indexado a inflacao (TIPS)"

        classe_rating, nota = _classificar_rating_emissor(descricao_norm)
        if classe_rating == "Emerging Markets":
            return "Emerging Markets", "alta", nota
        if classe_rating == "High Yield":
            return "High Yield", "alta", nota

        vencimento = maturity_date if maturity_date is not None else _maturidade_da_descricao(descricao)
        anos = _anos_ate_vencimento(vencimento)
        bucket = _bucket_prazo_ig(anos)
        if classe_rating == "Investment Grade":
            return bucket, "alta", nota
        # emissor nao encontrado na tabela pesquisada — assume Investment Grade pelo
        # prazo (decisao do usuario), mas marca confianca baixa pra aparecer na revisao.
        return bucket, "baixa", "Emissor nao encontrado na pesquisa de rating — revisar"

    eh_acao_individual = categoria_norm.strip() in ("STOCKS", "EQUITIES")
    if eh_acao_individual:
        ticker_norm = normalizar_chave(descricao)
        if ticker_norm in _EQUITY_EM:
            return "Equities EM", "alta", "Empresa sediada em mercado emergente"
        if ticker_norm in _EQUITY_GLOBAL or any(k in descricao_norm for k in _EQUITY_GLOBAL):
            return "Equities Global", "alta", "Empresa sediada fora dos EUA (desenvolvido)"
        return "Equities US", "alta", "Ação individual, padrão US (sem indicação de outra região)"

    eh_fundo_ou_etf = categoria_norm.strip() in (
        "ETF'S", "FUNDS", "UCITS", "INVESTMENT FUNDS"
    )
    if eh_fundo_ou_etf:
        ticker_norm = normalizar_chave(descricao)
        if ticker_norm in _TICKERS_ETF_AVENUE:
            return _TICKERS_ETF_AVENUE[ticker_norm], "alta", "ETF conhecido (Avenue, so ticker)"
        classe, confianca = _classificar_fundo_por_nome(descricao_norm)
        return classe, confianca, "Classificado por palavra-chave no nome do fundo"

    return None, "baixa", "Sem regra automatica — precisa classificacao manual"


def carregar_classificacao_manual(caminho):
    caminho = Path(caminho)
    if not caminho.exists():
        return pd.DataFrame(columns=["Chave", "Classe"])
    return pd.read_csv(caminho, dtype=str)


def salvar_classificacao_manual(caminho, df):
    df = df.dropna(subset=["Chave", "Classe"]).drop_duplicates(subset=["Chave"], keep="last")
    df.sort_values("Chave").to_csv(caminho, index=False)
    return df


def aplicar_classificacao(df, coluna_descricao, coluna_categoria_origem, manual_df, coluna_maturidade=None):
    """Aplica o classificador automatico e depois a tabela manual (que tem prioridade)."""
    df = df.copy()
    mapa_manual = dict(zip(manual_df["Chave"].apply(normalizar_chave), manual_df["Classe"]))

    classes, confiancas, notas = [], [], []
    for _, row in df.iterrows():
        descricao = row[coluna_descricao]
        chave = normalizar_chave(descricao)
        maturidade = row[coluna_maturidade] if coluna_maturidade else None
        classe_auto, confianca, nota = classificar_automatico(
            descricao, row[coluna_categoria_origem], maturidade
        )
        if chave in mapa_manual:
            classes.append(mapa_manual[chave])
            confiancas.append("manual")
            notas.append("Classificacao manual do usuario")
        else:
            classes.append(classe_auto)
            confiancas.append(confianca)
            notas.append(nota)

    df["Classe"] = classes
    df["Confiança"] = confiancas
    df["Nota Classificação"] = notas
    return df
