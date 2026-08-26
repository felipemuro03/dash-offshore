"""Acompanhamento de posicoes de Renda Fixa offshore (Bonds individuais) na Avenue e
no BTG US, com historico de marcacao salvo a cada snapshot (upload)."""

import datetime as dt
from pathlib import Path

import pandas as pd

COLUNAS_HISTORICO = [
    "Data", "Custodia", "Cliente", "Identificador", "Descricao",
    "Preco", "Valor Atual (US$)", "Valor Compra (US$)", "Variacao (US$)", "Variacao (%)",
]


def carregar_avenue(arquivo):
    """Le a aba 'Export' da planilha de posicoes em Bonds da Avenue (ja e so bonds)."""
    df = pd.read_excel(arquivo, sheet_name="Export", header=0)
    df = df.rename(columns={
        "Name": "Cliente",
        "ISIN": "Identificador",
        "Nome": "Descricao",
        "Valor Compra US$": "Valor Compra (US$)",
        "Valor Atual US$": "Valor Atual (US$)",
        "Variação %": "Variacao (%)",
    })
    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    df["Custodia"] = "Avenue"
    df["Preco"] = pd.NA
    return df[["Cliente", "Identificador", "Descricao", "Preco",
               "Valor Atual (US$)", "Valor Compra (US$)", "Variacao (%)", "Custodia"]]


def carregar_btg_us(arquivo):
    """Le a aba 'Holdings' do export de posicoes do BTG US e filtra Fixed Income.

    Esse formato (Holdings) substituiu o antigo 'UnrealizedGainLoss' (UGL) — ja vem com
    uma coluna 'Asset Classification' explicita (nao precisa mais adivinhar por regex na
    descricao) e uma linha por posicao, ja somando os lotes (confirmado: a mesma posicao
    que no UGL exigia somar 2 lotes + remover linhas duplicadas/fantasma aparece aqui
    numa unica linha, com o mesmo valor final) — bem mais simples e confiavel.
    """
    df = pd.read_excel(arquivo, sheet_name="Holdings", header=0)
    df = df[df["Asset Classification"] == "Fixed Income"].copy()

    df = df.rename(columns={
        "Account Nickname/Title": "Cliente",
        "CUSIP": "Identificador",
        "Description": "Descricao",
        "Price": "Preco",
        "Market Value": "Valor Atual (US$)",
    })
    # Essa planilha nao tem o custo de aquisicao direto, so o Gain/Loss $ — o custo e
    # derivado dai (Gain/Loss $ = Valor Atual - Valor Compra).
    df["Valor Compra (US$)"] = df["Valor Atual (US$)"] - df["Gain/Loss $"]
    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    df["Descricao"] = df["Descricao"].astype(str).str.strip()
    df["Custodia"] = "BTG US"
    df["Variacao (%)"] = df["Gain/Loss %"]
    return df[["Cliente", "Identificador", "Descricao", "Preco",
               "Valor Atual (US$)", "Valor Compra (US$)", "Variacao (%)", "Custodia"]]


def montar_snapshot(avenue_df, btg_df, data_snapshot=None):
    """Consolida Avenue + BTG US num snapshot, uma linha por posicao (Custodia +
    Cliente + Identificador) — soma lotes diferentes do mesmo bond do mesmo cliente
    em vez de deixar um por lote, senao um cliente com 2 lotes do mesmo bond perderia
    um deles ao salvar no historico (a chave do historico e por posicao, nao por lote).
    """
    partes = [d for d in (avenue_df, btg_df) if d is not None and not d.empty]
    if not partes:
        return pd.DataFrame(columns=COLUNAS_HISTORICO)
    consolidado = pd.concat(partes, ignore_index=True)

    agrupado = consolidado.groupby(
        ["Custodia", "Cliente", "Identificador", "Descricao"], as_index=False
    ).agg(
        Preco=("Preco", "mean"),
        **{
            "Valor Atual (US$)": ("Valor Atual (US$)", "sum"),
            "Valor Compra (US$)": ("Valor Compra (US$)", "sum"),
        },
    )
    # Variacao recalculada a partir da soma em US$ (nao e a media das % dos lotes,
    # que ficaria errada quando os lotes tem tamanhos diferentes). O agio/desagio em
    # US$ e simplesmente essa mesma diferenca, sem dividir pelo custo.
    agrupado["Variacao (US$)"] = agrupado["Valor Atual (US$)"] - agrupado["Valor Compra (US$)"]
    agrupado["Variacao (%)"] = agrupado["Variacao (US$)"] / agrupado["Valor Compra (US$)"]

    agrupado.insert(0, "Data", data_snapshot or dt.date.today().isoformat())
    return agrupado[COLUNAS_HISTORICO]


def carregar_historico(caminho):
    caminho = Path(caminho)
    if not caminho.exists():
        return pd.DataFrame(columns=COLUNAS_HISTORICO)
    return pd.read_csv(caminho, dtype={"Identificador": str})


def salvar_snapshot(caminho, historico_df, snapshot_df):
    """Acrescenta o snapshot de hoje ao historico, substituindo um snapshot ja salvo
    na mesma data pra mesma posicao (permite re-salvar no mesmo dia sem duplicar)."""
    combinado = pd.concat([historico_df, snapshot_df], ignore_index=True)
    combinado = combinado.drop_duplicates(
        subset=["Data", "Custodia", "Cliente", "Identificador"], keep="last"
    )
    combinado = combinado.sort_values(["Data", "Custodia", "Cliente"]).reset_index(drop=True)
    combinado.to_csv(caminho, index=False)
    return combinado


def ultimo_snapshot_por_posicao(historico_df):
    """Reconstroi o retrato mais recente de cada posicao a partir do historico."""
    if historico_df.empty:
        return historico_df
    return (
        historico_df.sort_values("Data")
        .groupby(["Custodia", "Cliente", "Identificador"], as_index=False)
        .last()
    )


def evolucao_posicao(historico_df, cliente, identificador):
    filtro = historico_df[
        (historico_df["Cliente"] == cliente) & (historico_df["Identificador"] == identificador)
    ].copy()
    return filtro.sort_values("Data").reset_index(drop=True)
