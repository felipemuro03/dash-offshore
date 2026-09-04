"""Revisao periodica de carteiras offshore (Avenue + BTG US) — retorno de 12 meses e
principal detrator por cliente, com historico salvo pra acompanhar ao longo do tempo.
Complementa Posicoes Consolidadas (mesma tela, aba Detalhe por Cliente)."""

import datetime as dt
from pathlib import Path

import pandas as pd

COLUNAS_HISTORICO = ["Data", "Custodia", "Cliente", "Número", "Retorno 12m", "Principal Detrator"]


def carregar_revisao(arquivo):
    """Le as abas 'Avenue' e 'BTG US' da planilha de revisao de carteiras."""
    partes = []
    for aba, custodia in (("Avenue", "Avenue"), ("BTG US", "BTG US")):
        df = pd.read_excel(arquivo, sheet_name=aba, header=0)
        df = df.rename(columns={
            "Nome da Conta": "Cliente",
            "12 meses": "Retorno 12m",
            "Principal detrator": "Principal Detrator",
        })
        df["Cliente"] = df["Cliente"].astype(str).str.strip()
        df["Custodia"] = custodia
        partes.append(df[["Custodia", "Cliente", "Número", "Retorno 12m", "Principal Detrator"]])
    return pd.concat(partes, ignore_index=True)


def montar_snapshot(revisao_df, data_snapshot=None):
    snapshot = revisao_df.copy()
    snapshot.insert(0, "Data", data_snapshot or dt.date.today().isoformat())
    return snapshot[COLUNAS_HISTORICO]


def carregar_historico(caminho):
    caminho = Path(caminho)
    if not caminho.exists():
        return pd.DataFrame(columns=COLUNAS_HISTORICO)
    return pd.read_csv(caminho, dtype={"Número": str})


def salvar_snapshot(caminho, historico_df, snapshot_df):
    """Acrescenta o snapshot de hoje ao historico, substituindo um snapshot ja salvo na
    mesma data pro mesmo cliente (permite re-salvar no mesmo dia sem duplicar)."""
    combinado = pd.concat([historico_df, snapshot_df], ignore_index=True)
    combinado = combinado.drop_duplicates(subset=["Data", "Custodia", "Cliente"], keep="last")
    combinado = combinado.sort_values(["Data", "Custodia", "Cliente"]).reset_index(drop=True)
    combinado.to_csv(caminho, index=False)
    return combinado


def historico_do_cliente(historico_df, cliente_posicao):
    """Historico de revisao de um cliente, do mais recente pro mais antigo, dado o nome
    como aparece nas posicoes. O 'Account Nickname/Title' do BTG US vem truncado (nome
    da conta cortado num tamanho fixo) e nao bate exatamente com o nome completo salvo
    na planilha de revisao — por isso tenta match exato primeiro e, se nao achar, checa
    se o nome da revisao COMEÇA com o nome truncado da posicao (so aceita se achar
    exatamente 1 cliente candidato, pra nao arriscar juntar 2 clientes diferentes)."""
    if historico_df.empty:
        return historico_df
    alvo = str(cliente_posicao).strip().upper()
    nomes_normalizados = historico_df["Cliente"].str.upper().str.strip()

    exato = historico_df[nomes_normalizados == alvo]
    if not exato.empty:
        return exato.sort_values("Data", ascending=False).reset_index(drop=True)

    mask_prefixo = nomes_normalizados.str.startswith(alvo)
    nomes_candidatos = nomes_normalizados[mask_prefixo].unique()
    if len(nomes_candidatos) == 1:
        return historico_df[mask_prefixo].sort_values("Data", ascending=False).reset_index(drop=True)

    return historico_df.iloc[0:0]
