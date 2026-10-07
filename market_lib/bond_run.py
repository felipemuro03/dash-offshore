"""Bond run (lista de ofertas) da Avenue e do BTG Pactual — le os PDFs, normaliza pro
mesmo schema e prepara os dados pra comparar oportunidades de alocacao (YTW, rating,
prazo, spread vs Treasury).

Os dois PDFs sao bem diferentes:
- BTG ("US Investment Grade List"): 1 linha de texto por bond, colunas fixas — da pra ler
  com regex a partir do texto extraido.
- Avenue ("bonds_list_us"): tabela sem linhas de grade, com celulas que quebram em varias
  linhas (nome do emissor, ticker). Aqui o texto corrido embaralha as colunas, entao as
  palavras sao agrupadas pela POSICAO na pagina: cada CUSIP (1 por bond, sempre numa linha
  so, na ultima coluna) ancora uma linha da tabela, e cada palavra vai pra linha do CUSIP
  mais proximo na vertical e pra coluna cujo x bate com o cabecalho da pagina.
"""

import bisect
import datetime as dt
import re

import numpy as np
import pandas as pd
import pdfplumber

# ---------- Rating ----------

ESCALA_RATING = [
    "AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
    "BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C", "D",
]
LIMITE_INVESTMENT_GRADE = ESCALA_RATING.index("BBB-") + 1

_MOODYS = {
    "Aaa": "AAA", "Aa1": "AA+", "Aa2": "AA", "Aa3": "AA-", "A1": "A+", "A2": "A", "A3": "A-",
    "Baa1": "BBB+", "Baa2": "BBB", "Baa3": "BBB-", "Ba1": "BB+", "Ba2": "BB", "Ba3": "BB-",
    "B1": "B+", "B2": "B", "B3": "B-", "Caa1": "CCC+", "Caa2": "CCC", "Caa3": "CCC-",
    "Ca": "CC", "C": "C",
}


def score_rating(rating):
    return ESCALA_RATING.index(rating) + 1 if rating in ESCALA_RATING else np.nan


def _rating_sp_fitch(segmento):
    """'A- *-' -> 'A-' ; 'A+u' (em revisao) -> 'A+' ; '-', 'WD', 'WR' -> None."""
    if not segmento or not segmento.strip():
        return None
    token = segmento.split()[0].rstrip("u").upper()
    return token if token in ESCALA_RATING else None


def _rating_moodys(segmento):
    if not segmento or not segmento.strip():
        return None
    return _MOODYS.get(segmento.split()[0])


def _interpretar_ratings_btg(texto):
    """'Baa1/BBB+/A-' (Moody's/S&P/Fitch; cada um pode vir '-', 'WD', ou com outlook tipo
    'A3 *-'). Devolve (rating representativo, pior rating das agencias, texto original).
    Representativo = S&P, senao Fitch, senao Moody's. Pior = a nota mais baixa entre as
    que existirem (criterio mais conservador)."""
    partes = [p.strip() for p in str(texto).split("/")]
    partes += [""] * (3 - len(partes))
    moodys, sp, fitch = _rating_moodys(partes[0]), _rating_sp_fitch(partes[1]), _rating_sp_fitch(partes[2])
    existentes = [r for r in (sp, fitch, moodys) if r]
    if not existentes:
        return None, None, texto
    pior = max(existentes, key=score_rating)
    return existentes[0], pior, texto


# ---------- Datas ----------

_MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
_MESES_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MESES_ABREV_EN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
                   "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def _ano_2_digitos(yy):
    # lista de ofertas so tem bond em aberto, entao vencimento e sempre futuro: 75 = 2075
    # (ex.: Alphabet 5.7% de 50 anos), nunca 1975.
    return 2000 + yy


def _data_btg(texto):
    """'2/8/2028' (M/D/AAAA) ou '01-Apr-31' (D-Mon-AA). '-' ou vazio -> None."""
    texto = (texto or "").strip()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
    if m:
        return dt.date(int(m[3]), int(m[1]), int(m[2]))
    m = re.fullmatch(r"(\d{1,2})-([A-Za-z]{3})-(\d{2})", texto)
    if m and m[2].lower() in _MESES_ABREV_EN:
        return dt.date(_ano_2_digitos(int(m[3])), _MESES_ABREV_EN[m[2].lower()], int(m[1]))
    return None


def _data_avenue_curta(texto):
    """'30/09/28' (DD/MM/AA)."""
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{2})", (texto or "").strip())
    return dt.date(_ano_2_digitos(int(m[3])), int(m[2]), int(m[1])) if m else None


def _data_avenue_longa(texto):
    """'01-02-2034' (DD-MM-AAAA). '-' ou vazio -> None."""
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", (texto or "").strip())
    return dt.date(int(m[3]), int(m[2]), int(m[1])) if m else None


def _data_referencia_avenue(texto):
    m = re.search(r"atualizadas em:\s*(\d{1,2}) de (\w+) de (\d{4})", texto, flags=re.IGNORECASE)
    if m and m[2].lower() in _MESES_PT:
        return dt.date(int(m[3]), _MESES_PT[m[2].lower()], int(m[1]))
    return None


def _data_referencia_btg(texto):
    m = re.search(r"([A-Za-z]+) (\d{1,2}), (\d{4})", texto)
    if m and m[1].lower() in _MESES_EN:
        return dt.date(int(m[3]), _MESES_EN[m[1].lower()], int(m[2]))
    return None


# ---------- BTG ----------

_RE_BTG = re.compile(
    r"^(?P<emissor>.+?)\s+(?P<ticker>\S+)\s+(?P<cupom>[\d.]+)%\s+(?P<venc>\S+)\s+(?P<call>\S+)\s+"
    r"(?P<bid>[\d.]+)\s+(?P<ask>[\d.]+)\s+(?P<ytw_bid>-?[\d.]+)%\s+(?P<ytw_ask>-?[\d.]+)%\s+"
    r"(?P<duration>[\d.]+)\s+(?P<minimo>\d+)\s+(?P<ratings>.+?)\s+(?P<tipo>[A-Z][A-Z\-]+)\s+"
    r"(?P<setor>.+?)\s+(?P<isin>[A-Z]{2}[0-9A-Z]{9}[0-9])$"
)


def _cusip_de_isin(isin):
    """Pra ISIN dos EUA/Canada o miolo de 9 caracteres e o CUSIP; pra outros paises nao
    e — nesses casos usa o proprio ISIN como chave (nao vai casar com a Avenue, que so
    informa CUSIP, mas tambem nao gera casamento errado)."""
    return isin[2:11] if isin[:2] in ("US", "CA") else isin


def carregar_run_btg(arquivo):
    """Le o PDF 'US Investment Grade List' do BTG Pactual. Devolve (DataFrame, data_ref,
    linhas_nao_lidas) — linhas_nao_lidas e a lista de linhas que pareciam um bond (terminam
    em ISIN) mas nao bateram com o formato esperado, pra aparecer na tela em vez de sumir."""
    linhas_texto, data_ref = [], None
    with pdfplumber.open(arquivo) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            if data_ref is None:
                data_ref = _data_referencia_btg(texto)
            linhas_texto.extend(texto.splitlines())

    registros, nao_lidas = [], []
    for linha in linhas_texto:
        if not re.search(r"\s[A-Z]{2}[0-9A-Z]{9}[0-9]$", linha):
            continue
        m = _RE_BTG.match(linha)
        if not m:
            nao_lidas.append(linha)
            continue
        rating, rating_pior, ratings_txt = _interpretar_ratings_btg(m["ratings"])
        registros.append({
            "Fonte": "BTG",
            "Emissor": m["emissor"].strip(),
            "Ticker": m["ticker"],
            "Cupom": float(m["cupom"]),
            "Vencimento": _data_btg(m["venc"]),
            "Proxima Chamada": _data_btg(m["call"]),
            "Preco": float(m["ask"]),
            "YTW": float(m["ytw_ask"]),
            "Duration": float(m["duration"]),
            "Rating": rating,
            "Rating (pior)": rating_pior,
            "Ratings (Moody's/S&P/Fitch)": ratings_txt,
            "Senioridade": None,
            "Minimo (US$)": float(m["minimo"]),
            "Setor": m["setor"].strip(),
            "Tipo de Cupom": m["tipo"],
            "ISIN": m["isin"],
            "CUSIP": _cusip_de_isin(m["isin"]),
        })
    # o mesmo bond as vezes aparece 2x identico na lista (ex.: DGX 6.4 2033) — mantem 1
    return pd.DataFrame(registros).drop_duplicates(subset="CUSIP", keep="first"), data_ref, nao_lidas


# ---------- Avenue ----------

# Posicao x0 (em pontos) de cada cabecalho de coluna — valores medidos no PDF real; usados
# so como reserva caso o cabecalho de uma pagina nao seja encontrado.
_X_PADRAO_AVENUE = {
    "setor": 18.7, "emissor": 103.1, "ticker": 182.0, "preco": 243.0, "ytw": 272.6,
    "duration": 297.9, "rating": 340.3, "ig": 373.2, "senioridade": 413.1,
    "minimo": 466.6, "chamada": 493.6, "cusip": 550.0,
}
_CABECALHO_AVENUE = {
    "Industria": "setor", "Nome": "emissor", "Ticker": "ticker", "Offer": "preco", "YTW": "ytw",
    "Duration": "duration", "Rating": "rating", "Invest": "ig", "Seniority": "senioridade",
    "Min": "minimo", "Data": "chamada", "CUSIP": "cusip",
}
_ORDEM_COLUNAS_AVENUE = list(_X_PADRAO_AVENUE)
_RE_CUSIP = re.compile(r"^[0-9A-Z]{8}[0-9]$")
_RE_TICKER_AVENUE = re.compile(
    r"^(?P<simbolo>.+?)\s+(?P<cupom>[\d.]+)\s+(?P<venc>\d{2}/\d{2}/\d{2}|PERP)$"
)


def _numero_br(texto):
    """'99,21' -> 99.21 ; '3,21%' -> 3.21 ; '0.25' (duration vem com ponto) -> 0.25 ;
    '-' ou vazio -> NaN."""
    texto = (texto or "").replace("%", "").strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return np.nan


def _linhas_pagina_avenue(pagina):
    palavras = pagina.extract_words()
    topo_rodape = min((w["top"] for w in palavras if w["text"].startswith("Fonte:")), default=pagina.height)

    x_cusip = _X_PADRAO_AVENUE["cusip"]
    ancoras = [
        w for w in palavras
        if _RE_CUSIP.match(w["text"]) and w["x0"] >= x_cusip - 8 and w["top"] < topo_rodape
    ]
    if not ancoras:
        return []

    corte_cabecalho = min(a["top"] for a in ancoras) - 14
    cabecalho = [w for w in palavras if w["top"] < corte_cabecalho]
    x_colunas = dict(_X_PADRAO_AVENUE)
    achados = {}
    for w in cabecalho:
        coluna = _CABECALHO_AVENUE.get(w["text"])
        if coluna and coluna not in achados:
            achados[coluna] = w["x0"]
    if len(achados) == len(_X_PADRAO_AVENUE):
        x_colunas = achados
    limites = [x_colunas[c] for c in _ORDEM_COLUNAS_AVENUE]

    celulas = [{c: [] for c in _ORDEM_COLUNAS_AVENUE} for _ in ancoras]
    for w in palavras:
        if w["top"] < corte_cabecalho or w["top"] >= topo_rodape:
            continue
        distancias = [abs(w["top"] - a["top"]) for a in ancoras]
        i = int(np.argmin(distancias))
        if distancias[i] > 20:
            continue
        centro = (w["x0"] + w["x1"]) / 2
        j = max(bisect.bisect_right(limites, centro) - 1, 0)
        celulas[i][_ORDEM_COLUNAS_AVENUE[j]].append(w)

    linhas = []
    for linha in celulas:
        texto = {
            coluna: " ".join(
                w["text"] for w in sorted(palavras_col, key=lambda p: (int(p["top"] // 3), p["x0"]))
            )
            for coluna, palavras_col in linha.items()
        }
        linhas.append(texto)
    return linhas


def carregar_run_avenue(arquivo):
    """Le o PDF 'bonds_list_us' da Avenue. Devolve (DataFrame, data_ref, linhas_nao_lidas)."""
    brutas, data_ref = [], None
    with pdfplumber.open(arquivo) as pdf:
        for pagina in pdf.pages:
            if data_ref is None:
                data_ref = _data_referencia_avenue(pagina.extract_text() or "")
            brutas.extend(_linhas_pagina_avenue(pagina))

    registros, nao_lidas = [], []
    for b in brutas:
        m = _RE_TICKER_AVENUE.match(b["ticker"])
        if not m:
            nao_lidas.append(" | ".join(f"{k}={v}" for k, v in b.items()))
            continue
        rating = _rating_sp_fitch(b["rating"])
        registros.append({
            "Fonte": "Avenue",
            "Emissor": b["emissor"],
            "Ticker": m["simbolo"],
            "Cupom": float(m["cupom"]),
            "Vencimento": _data_avenue_curta(m["venc"]),
            "Proxima Chamada": _data_avenue_longa(b["chamada"]),
            "Preco": _numero_br(b["preco"]),
            "YTW": _numero_br(b["ytw"]),
            "Duration": _numero_br(b["duration"]),
            "Rating": rating,
            "Rating (pior)": rating,
            "Ratings (Moody's/S&P/Fitch)": b["rating"],
            "Senioridade": b["senioridade"] or None,
            # Min Qty da Avenue = qtd de bonds de US$ 1.000 de face — conferido contra os
            # bonds que aparecem nas 2 listas (Avenue 1 <-> BTG 1.000, Avenue 2 <-> 2.000).
            "Minimo (US$)": _numero_br(b["minimo"]) * 1000,
            "Setor": b["setor"],
            "Tipo de Cupom": None,
            "ISIN": None,
            "CUSIP": b["cusip"],
            "IG (Avenue)": b["ig"],
        })
    return pd.DataFrame(registros), data_ref, nao_lidas


# ---------- Consolidacao + spread ----------

_COLUNAS_RUN = [
    "CUSIP", "Emissor", "Ticker", "Cupom", "Vencimento", "Proxima Chamada", "Preco", "YTW",
    "Duration", "Rating", "Rating (pior)", "Ratings (Moody's/S&P/Fitch)", "Senioridade",
    "Minimo (US$)", "Setor", "Tipo de Cupom", "ISIN",
]


_COLUNAS_NUMERICAS_RUN = ["Cupom", "Preco", "YTW", "Duration", "Minimo (US$)"]


def _preparar(df):
    """Frame de uma casa so com as colunas do schema comum, indexado por CUSIP. Quando a
    casa nao foi subida (df vazio) as colunas numericas ficariam 'object' e qualquer
    comparacao/np.fmax contra elas falha em silencio (todo bond some nos filtros) —
    por isso forca float."""
    if df is None or df.empty:
        df = pd.DataFrame(columns=_COLUNAS_RUN)
    saida = df.reindex(columns=_COLUNAS_RUN).set_index("CUSIP")
    for coluna in _COLUNAS_NUMERICAS_RUN:
        saida[coluna] = pd.to_numeric(saida[coluna], errors="coerce")
    return saida


def curva_treasury(avenue_df):
    """Pontos (duration, YTW) dos Treasuries da propria lista da Avenue, usados como curva
    livre de risco aproximada pra calcular spread. So existe se a Avenue foi carregada."""
    if avenue_df is None or avenue_df.empty:
        return None
    tsy = avenue_df[
        (avenue_df["Emissor"] == "United States of America") & avenue_df["Ticker"].isin(["T", "B"])
    ].dropna(subset=["Duration", "YTW"])
    if len(tsy) < 2:
        return None
    return tsy.sort_values("Duration").drop_duplicates("Duration")[["Duration", "YTW"]].reset_index(drop=True)


def consolidar_runs(avenue_df, btg_df, data_ref=None):
    """Uma linha por CUSIP. Pra quem aparece nas duas listas, guarda preco/YTW de cada casa
    lado a lado e marca qual tem o melhor YTW (Casa). 'Spread vs UST' = YTW da melhor casa
    menos o YTW dos Treasuries da Avenue interpolado na duration do bond (aproximado: a
    curva vem de ofertas da Avenue, nao de um fechamento oficial; pra duration acima do
    maior Treasury da lista usa o ultimo ponto, entao o spread dos bonds muito longos e
    so indicativo)."""
    a, b = _preparar(avenue_df), _preparar(btg_df)
    chaves = a.index.union(b.index)
    a, b = a.reindex(chaves), b.reindex(chaves)

    def preferir_avenue(coluna):
        return a[coluna].where(a[coluna].notna(), b[coluna])

    tab = pd.DataFrame(index=chaves)
    for coluna in ("Emissor", "Ticker", "Cupom", "Vencimento", "Setor", "Proxima Chamada"):
        tab[coluna] = preferir_avenue(coluna)
    tab["Senioridade"] = a["Senioridade"]
    tab["Tipo de Cupom"] = b["Tipo de Cupom"]
    tab["ISIN"] = b["ISIN"]

    tab["Preço Avenue"], tab["YTW Avenue"], tab["Duration Avenue"] = a["Preco"], a["YTW"], a["Duration"]
    tab["Preço BTG"], tab["YTW BTG"], tab["Duration BTG"] = b["Preco"], b["YTW"], b["Duration"]
    tab["Rating Avenue"] = a["Rating"]
    tab["Rating BTG"] = b["Rating"]
    tab["Ratings BTG (Moody's/S&P/Fitch)"] = b["Ratings (Moody's/S&P/Fitch)"]

    tem_a, tem_b = a["YTW"].notna(), b["YTW"].notna()
    tab["Fontes"] = np.select(
        [tem_a & tem_b, tem_a, tem_b], ["Avenue + BTG", "Avenue", "BTG"], default="-"
    )
    tab["YTW"] = np.fmax(a["YTW"], b["YTW"])
    btg_melhor = tem_b & (~tem_a | (b["YTW"] > a["YTW"]))
    avenue_melhor = tem_a & (~tem_b | (a["YTW"] > b["YTW"]))
    tab["Casa"] = np.select([btg_melhor, avenue_melhor, tem_a & tem_b], ["BTG", "Avenue", "Empate"], default="-")
    usar_btg = tab["Casa"] == "BTG"
    tab["Preço"] = np.where(usar_btg, b["Preco"], a["Preco"])
    tab["Duration"] = np.where(usar_btg, b["Duration"], a["Duration"])
    tab["Dif. YTW BTG−Avenue (bps)"] = (b["YTW"] - a["YTW"]) * 100

    # rating: nota de referencia (Avenue composto; sem Avenue, S&P→Fitch→Moody's do BTG) e
    # pior nota entre todas as agencias/fontes disponiveis (criterio conservador)
    nota_ref_a, nota_ref_b = a["Rating"].map(score_rating), b["Rating"].map(score_rating)
    tab["Nota (referência)"] = nota_ref_a.where(nota_ref_a.notna(), nota_ref_b)
    tab["Nota (pior)"] = pd.concat(
        [a["Rating (pior)"].map(score_rating), b["Rating (pior)"].map(score_rating)], axis=1
    ).max(axis=1, skipna=True)

    tab["Mínimo (US$)"] = b["Minimo (US$)"].where(b["Minimo (US$)"].notna(), a["Minimo (US$)"])

    ref = pd.Timestamp(data_ref) if data_ref else pd.Timestamp(dt.date.today())
    venc = pd.to_datetime(tab["Vencimento"])
    tab["Prazo (anos)"] = (venc - ref).dt.days / 365.25

    curva = curva_treasury(avenue_df)
    if curva is not None:
        taxa_ust = np.interp(tab["Duration"].astype(float), curva["Duration"], curva["YTW"])
        tab["Spread vs UST (bps)"] = (tab["YTW"] - taxa_ust) * 100
        tab.loc[tab["Emissor"].isin(["United States of America", "US Treasury TIPS"]), "Spread vs UST (bps)"] = np.nan
    else:
        tab["Spread vs UST (bps)"] = np.nan

    return tab.reset_index(names="CUSIP")


def rotulo_rating(nota):
    return ESCALA_RATING[int(nota) - 1] if pd.notna(nota) else "NR"
