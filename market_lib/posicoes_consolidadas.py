"""Posicoes consolidadas offshore (Avenue + BTG US), todos os ativos — visao de cliente,
exposicao e classificacao por classe. Complementa o Fixed Income (que so olha bonds)."""

import pandas as pd

from market_lib import classificacao

LIMITE_LIQUIDEZ_PADRAO = 0.10


def carregar_avenue_data(arquivo):
    """Le a aba 'Export' do export 'Data' da Avenue — todos os produtos (Bonds, Stocks,
    ETF's, Funds, UCITs, Digital Assets). Os 4 tipos de 'Balance' (saldo na conta banking
    do cliente, nao e uma posicao de investimento) sao descartados por completo — nao
    contam como liquidez nem entram em nenhuma classificacao, por pedido explicito do
    usuario (esse saldo distorcia o perfil de liquidez)."""
    df = pd.read_excel(arquivo, sheet_name="Export", header=0)
    # A planilha tem linhas de rodape/total no final (Cliente e todo o resto em branco,
    # so um valor solto) — nao sao posicoes reais, tem que descartar antes de somar.
    df = df.dropna(subset=["Nome do Cliente"]).copy()
    df = df[~df["Produto"].astype(str).str.startswith("Balance")].copy()
    df = df.rename(columns={
        "Nome do Cliente": "Cliente",
        "Produto": "Categoria",
        "Nome do Produto": "Descricao",
        "Valor Produto": "Valor Atual (US$)",
    })
    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    df["Descricao"] = df["Descricao"].astype(str).str.strip()
    df["Custodia"] = "Avenue"
    df["Maturity Date"] = pd.NaT
    return df[["Cliente", "Ticker", "Descricao", "Categoria", "Valor Atual (US$)", "Custodia", "Maturity Date"]]


def carregar_btg_holdings(arquivo):
    """Le a aba 'Holdings' do BTG US — todos os ativos (Fixed Income, Equities,
    Investment Funds, Alternative Investments, Cash/Money Funds)."""
    df = pd.read_excel(arquivo, sheet_name="Holdings", header=0)
    df = df.rename(columns={
        "Account Nickname/Title": "Cliente",
        "CUSIP": "Ticker",
        "Description": "Descricao",
        "Asset Classification": "Categoria",
        "Market Value": "Valor Atual (US$)",
    })
    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    df["Descricao"] = df["Descricao"].astype(str).str.strip()
    df["Custodia"] = "BTG US"
    return df[["Cliente", "Ticker", "Descricao", "Categoria", "Valor Atual (US$)", "Custodia", "Maturity Date"]]


def montar_posicoes(avenue_df, btg_df, manual_df):
    partes = [d for d in (avenue_df, btg_df) if d is not None and not d.empty]
    if not partes:
        return pd.DataFrame(columns=[
            "Cliente", "Custodia", "Ticker", "Descricao", "Categoria",
            "Valor Atual (US$)", "Classe", "Confiança", "Nota Classificação",
        ])
    consolidado = pd.concat(partes, ignore_index=True)
    consolidado = classificacao.aplicar_classificacao(
        consolidado, "Descricao", "Categoria", manual_df, coluna_maturidade="Maturity Date"
    )
    return consolidado


def calcular_liquidez_por_cliente(posicoes_df, limite=LIMITE_LIQUIDEZ_PADRAO):
    """Por cliente: patrimonio total, quanto esta em Money Markets, % de liquidez e
    quanto precisa reduzir pra voltar ao limite (0 se ja estiver dentro)."""
    patrimonio = posicoes_df.groupby("Cliente")["Valor Atual (US$)"].sum()
    liquidez = (
        posicoes_df[posicoes_df["Classe"] == "Money Markets"]
        .groupby("Cliente")["Valor Atual (US$)"]
        .sum()
    )
    tabela = pd.DataFrame({"Patrimônio Total": patrimonio})
    tabela["Money Markets"] = liquidez
    tabela["Money Markets"] = tabela["Money Markets"].fillna(0)
    tabela["% Liquidez"] = tabela["Money Markets"] / tabela["Patrimônio Total"]
    tabela["Reduzir (US$)"] = (
        tabela["Money Markets"] - limite * tabela["Patrimônio Total"]
    ).clip(lower=0)
    return tabela.reset_index().sort_values("% Liquidez", ascending=False)
