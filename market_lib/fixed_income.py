"""Acompanhamento de posicoes de Renda Fixa offshore (Bonds individuais) na Avenue e
no BTG US, com historico de marcacao salvo a cada snapshot (upload)."""

import datetime as dt
import re
from pathlib import Path

import pandas as pd

COLUNAS_HISTORICO = [
    "Data", "Custodia", "Cliente", "Identificador", "Descricao",
    "Preco", "Valor Atual (US$)", "Valor Compra (US$)", "Variacao (US$)", "Variacao (%)",
]

_PADRAO_DATA_BOND = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}")
_PADRAO_EXCLUIR_FUNDO = re.compile(r"\b(FUND|ETF|UCITS|FD)\b")


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


def _eh_bond_individual(descricao):
    # Bonds individuais tem data de vencimento na descricao ("... 06/19/41 ...");
    # fundos/ETFs que investem em bonds tambem podem ter "BOND" no nome mas nao tem
    # essa data, ou dizem explicitamente FUND/ETF/FD/UCITS — excluidos por isso.
    descricao = str(descricao or "")
    return bool(_PADRAO_DATA_BOND.search(descricao)) and not _PADRAO_EXCLUIR_FUNDO.search(descricao)


def _remover_lote_fantasma(df):
    """Confirmado nos dados reais (85 de 85 casos checados, sem excecao): quando uma
    posicao (mesmo Security + Account Number + Quantity + Total Cost + Market Value)
    aparece 2x, uma linha tem 'Lot #' == 'N/A' e a outra tem o codigo real do lote —
    e a MESMA posicao duplicada pelo export do BTG (nao 2 lotes diferentes, os valores
    batem identicos). Mantem so a linha com lote real quando existe par; se uma posicao
    so tiver a linha 'N/A' (sem par), mantem ela mesmo assim, pra nao perder a posicao.
    """
    df = df.copy()
    # O pandas le a celula com o texto "N/A" como NaN por padrao (esta na lista
    # default de na_values do read_excel) — comparar com a string "N/A" nunca bate,
    # tem que checar nulo mesmo.
    tem_lote_real = df["Lot #"].notna()
    # Total Cost/Market Value das duas linhas "iguais" as vezes diferem numa casa
    # decimal bem distante (ponto flutuante) mesmo mostrando o mesmo valor arredondado
    # — por isso a chave de comparacao usa os valores arredondados a 2 casas, nao os
    # brutos (senao o par nunca bate e nada e removido).
    chave = [
        df["Security"], df["Account Number"], df["Quantity"].round(4),
        df["Total Cost"].round(2), df["Market Value"].round(2),
    ]
    # groupby(...).apply() aqui descartava as colunas da chave do resultado (peculiaridade
    # do pandas quando a funcao aplicada devolve um subconjunto do grupo) — por isso o
    # filtro e feito de forma vetorizada com transform, sem apply.
    grupo_tem_algum_real = tem_lote_real.groupby(chave, dropna=False).transform("any")
    manter = tem_lote_real | ~grupo_tem_algum_real
    return df[manter]


def carregar_btg_us(arquivo):
    """Le a aba 'UGL' do Unrealized Gain/Loss do BTG US e filtra so bonds individuais.

    Tres limpezas necessarias, confirmadas nos dados reais:
    1. Linhas com 'Account Number' == 'Multiple' sao subtotal agregado de todas as
       contas que tem aquele titulo — mantidas fora, senao duplica a exposicao (o
       subtotal bate exatamente com a soma das contas individuais).
    2. A planilha tem algumas linhas duplicadas de verdade (linha inteira repetida,
       inclusive o mesmo Lot #) — removidas.
    3. Toda posicao aparece de novo como uma linha "fantasma" com Lot # == 'N/A' e o
       mesmo valor economico da linha real (ver _remover_lote_fantasma) — removida.
       Sem essa limpeza, o valor de mercado total ficava dobrado nessas posicoes.
    """
    df = pd.read_excel(arquivo, sheet_name="UGL", header=0)
    df = df[df["Account Number"].astype(str) != "Multiple"].copy()
    df = df[df["Symbol Description"].apply(_eh_bond_individual)].copy()
    df = df.drop_duplicates()
    df = _remover_lote_fantasma(df)

    df = df.rename(columns={
        "Account Nickname": "Cliente",
        "Security": "Identificador",
        "Symbol Description": "Descricao",
        "Last Price": "Preco",
        "Market Value": "Valor Atual (US$)",
        "Total Cost": "Valor Compra (US$)",
        "Unrealized Gain/Loss (%)": "Variacao (%)",
    })
    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    df["Descricao"] = df["Descricao"].astype(str).str.strip()
    df["Custodia"] = "BTG US"
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
