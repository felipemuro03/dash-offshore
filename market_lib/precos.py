"""Busca de precos (yfinance) e calculo de variacoes/universo de ativos.

Nenhuma funcao aqui usa @st.cache_data diretamente — quem chama (as paginas)
decide o cache, do mesmo jeito que fred_lib/client.py.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


def carregar_universo(caminho_csv: str) -> pd.DataFrame:
    """Le o universo curado de ativos (Ticker/Categoria/Subcategoria/Duration_Bucket/Descricao)."""
    df = pd.read_csv(caminho_csv)
    df["Ticker"] = df["Ticker"].astype(str).str.strip().str.upper()
    return df


def buscar_precos(tickers, data_inicio) -> pd.DataFrame:
    """Retorna DataFrame de precos de fechamento (colunas = tickers).

    auto_adjust=False: usa o preco de fechamento "puro" (ajustado so por
    splits, nao por dividendos) — mesma variacao que aparece no resumo da
    Yahoo Finance.
    """
    tickers = list(tickers)
    dados = yf.download(tickers, start=data_inicio, auto_adjust=False, progress=False)
    if isinstance(dados.columns, pd.MultiIndex):
        precos = dados["Close"]
    else:
        precos = dados[["Close"]]
        precos.columns = tickers
    return precos.dropna(how="all")


def buscar_nomes(tickers) -> dict:
    nomes = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            nomes[t] = info.get("longName") or info.get("shortName") or t
        except Exception:
            nomes[t] = t
    return nomes


def validar_ticker(ticker: str) -> dict:
    """Confere se o ticker existe no Yahoo Finance. Usa historico de preco (mais
    confiavel que .info, que pode vir vazio mesmo para tickers validos) para
    decidir se existe; nome legivel e best-effort."""
    ticker = ticker.strip().upper()
    try:
        historico = yf.Ticker(ticker).history(period="5d")
    except Exception:
        return {"valido": False, "nome": None}
    if historico.empty:
        return {"valido": False, "nome": None}
    nome = ticker
    try:
        info = yf.Ticker(ticker).info
        nome = info.get("longName") or info.get("shortName") or ticker
    except Exception:
        pass
    return {"valido": True, "nome": nome}


def adicionar_ticker_ao_universo(caminho_csv, ticker: str, categoria: str, subcategoria: str,
                                  duration_bucket: str, descricao: str) -> bool:
    """Acrescenta um ticker ao universo_ativos.csv. Retorna False se ja existir."""
    df = carregar_universo(caminho_csv)
    ticker = ticker.strip().upper()
    if ticker in df["Ticker"].values:
        return False
    nova_linha = pd.DataFrame([{
        "Ticker": ticker,
        "Categoria": categoria,
        "Subcategoria": subcategoria or "-",
        "Duration_Bucket": duration_bucket or "-",
        "Descricao": descricao or "-",
    }])
    df = pd.concat([df, nova_linha], ignore_index=True)
    df.to_csv(caminho_csv, index=False)
    return True


def variacao_percentual(serie: pd.Series, dias: int) -> float:
    if len(serie) < 2:
        return np.nan
    data_alvo = serie.index[-1] - pd.Timedelta(days=dias)
    base = serie[serie.index <= data_alvo]
    if base.empty:
        return np.nan
    preco_base = base.iloc[-1]
    preco_atual = serie.iloc[-1]
    return (preco_atual / preco_base - 1) * 100


def variacao_dias_uteis(serie: pd.Series, dias_uteis: int) -> float:
    """Variacao percentual usando N pregoes (dias uteis) mais recentes, contando linhas
    da serie em vez de dias corridos — mesma convencao que o Yahoo Finance usa pra '5D'.
    variacao_percentual(dias corridos) pode pegar uma base de comparacao bem diferente
    quando o corte de N dias corridos cai perto de um fim de semana/feriado com o preco
    tendo se mexido bastante logo antes: ex. BITO, corte em 7 dias corridos comparou
    contra um pico isolado de 1 dia (11.01) e deu -5.9%, enquanto os ultimos 5 pregões
    (a mesma janela que o Yahoo mostra) deram -0.34%."""
    serie = serie.dropna()
    if len(serie) <= dias_uteis:
        return np.nan
    preco_base = serie.iloc[-(dias_uteis + 1)]
    preco_atual = serie.iloc[-1]
    return (preco_atual / preco_base - 1) * 100


def variacao_ytd(serie: pd.Series) -> float:
    ano_atual = serie.index[-1].year
    antes_do_ano = serie[serie.index.year < ano_atual]
    if antes_do_ano.empty:
        return np.nan
    preco_base = antes_do_ano.iloc[-1]
    preco_atual = serie.iloc[-1]
    return (preco_atual / preco_base - 1) * 100


def montar_tabela_performance(precos: pd.DataFrame, universo: pd.DataFrame, nomes: dict) -> pd.DataFrame:
    """Monta a tabela de performance (preco atual + variacoes) cruzando com o universo curado."""
    linhas = []
    for _, linha_universo in universo.iterrows():
        ticker = linha_universo["Ticker"]
        if ticker not in precos.columns:
            continue
        serie = precos[ticker].dropna()
        if serie.empty:
            continue
        preco_atual = serie.iloc[-1]
        linhas.append(
            {
                "Ticker": ticker,
                "Nome": nomes.get(ticker, ticker),
                "Categoria": linha_universo["Categoria"],
                "Subcategoria": linha_universo["Subcategoria"],
                "Duration_Bucket": linha_universo["Duration_Bucket"],
                "Descricao": linha_universo.get("Descricao", ""),
                "Preco Atual (US$)": preco_atual,
                "Variacao 1 Semana (%)": variacao_dias_uteis(serie, 5),
                "Variacao 1 Mes (%)": variacao_percentual(serie, 30),
                "Variacao YTD (%)": variacao_ytd(serie),
                "Variacao 1 Ano (%)": variacao_percentual(serie, 365),
            }
        )
    return pd.DataFrame(linhas)
