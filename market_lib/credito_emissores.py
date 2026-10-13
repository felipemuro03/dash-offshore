"""Indicadores de credito de emissores dos EUA a partir das metricas brutas da SEC
(`sec_edgar.calcular_metricas_bruto`): alavancagem, cobertura de juros, liquidez, fluxo de
caixa livre (corporativas) e capitalizacao/retorno (bancos e financeiras), mais um semaforo
de referencia.

O semaforo e REGRA DE BOLSO (limites abaixo) — serve pra ordenar o que olhar primeiro, nao
substitui a analise: utilities/telecom/cable operam estruturalmente mais alavancadas (por isso
tem um perfil proprio) e financeiras nao tem semaforo (comparar entre pares)."""

import numpy as np
import pandas as pd

# (verde ate/desde, amarelo ate/desde). Alavancagem: menor e melhor; cobertura e liquidez: maior e melhor.
LIMITES = {
    "Padrão": {"alavancagem": (2.0, 4.0), "cobertura": (6.0, 3.0), "liquidez": (1.2, 0.9)},
    "Alavancagem estruturalmente alta": {"alavancagem": (4.0, 6.0), "cobertura": (4.0, 2.5), "liquidez": (1.0, 0.7)},
}
VERDE, AMARELO, VERMELHO, CINZA = "🟢", "🟡", "🔴", "⚪"


def _col(df, nome):
    return df[nome] if nome in df else pd.Series(np.nan, index=df.index)


def _dividir(num, den, minimo_den=0.0):
    num, den = pd.to_numeric(num, errors="coerce"), pd.to_numeric(den, errors="coerce")
    return (num / den).where(den > minimo_den)


def indicadores_corporativa(bruto):
    """Uma linha por periodo (mesma ordem de `bruto`, mais recente primeiro)."""
    d = bruto
    ebit_op, lair = _col(d, "resultado_operacional"), _col(d, "lucro_antes_ir")
    juros, juros_liq = _col(d, "juros"), _col(d, "juros_liquidos_sinal")

    # empresas sem linha de resultado operacional (J&J, IBM, Nike...): EBIT aproximado
    proxy = np.where(juros_liq.notna(), lair - juros_liq, np.where(juros.notna(), lair + juros, lair))
    ebit = ebit_op.where(ebit_op.notna(), pd.Series(proxy, index=d.index))
    ebit_fonte = np.where(
        ebit_op.notna(), "resultado operacional",
        np.where(lair.isna(), "",
                 np.where(juros_liq.notna(), "lucro antes do IR − juros líquidos",
                          np.where(juros.notna(), "lucro antes do IR + despesa de juros", "lucro antes do IR"))),
    )

    dep = _col(d, "depreciacao")
    ebitda = ebit + dep
    caixa_total = _col(d, "caixa").add(_col(d, "aplicacoes_cp").fillna(0), fill_value=np.nan).where(_col(d, "caixa").notna())
    divida = _col(d, "divida_bruta")
    divida_liq = divida - caixa_total
    fcl = _col(d, "fco") - _col(d, "capex")
    pl = _col(d, "patrimonio_liquido")

    saida = pd.DataFrame({
        "Fim do período": d["Fim do período"],
        "Receita (LTM)": _col(d, "receita"),
        "EBIT (LTM)": ebit,
        "D&A (LTM)": dep,
        "EBITDA (LTM)": ebitda,
        "Margem EBITDA": _dividir(ebitda, _col(d, "receita")),
        "Lucro líquido (LTM)": _col(d, "lucro_liquido"),
        "Caixa operacional (LTM)": _col(d, "fco"),
        "Capex (LTM)": _col(d, "capex"),
        "Fluxo de caixa livre (LTM)": fcl,
        "Caixa e aplicações": caixa_total,
        "Dívida bruta": divida,
        "Dívida líquida": divida_liq,
        "Dívida líquida/EBITDA": _dividir(divida_liq, ebitda).where(ebitda > 0),
        "Dívida bruta/EBITDA": _dividir(divida, ebitda).where(ebitda > 0),
        "Cobertura de juros (EBITDA/juros)": _dividir(ebitda, juros).where(ebitda > 0),
        "Cobertura de juros (EBIT/juros)": _dividir(ebit, juros),
        "FCL/Dívida bruta": _dividir(fcl, divida),
        "Liquidez corrente": _dividir(_col(d, "ativo_circulante"), _col(d, "passivo_circulante")),
        "Dívida/(Dívida+PL)": _dividir(divida, divida + pl).where(pl > 0),
        "Patrimônio líquido": pl,
        "Ativo total": _col(d, "ativo_total"),
        "Juros (LTM)": juros,
        "Fonte do EBIT": ebit_fonte,
        "Fonte da D&A": _col(d, "depreciacao_fonte"),
        "Fonte dos juros": _col(d, "juros_fonte"),
        "Data-base da dívida": _col(d, "divida_data_base"),
    })
    return saida


def indicadores_financeira(bruto):
    d = bruto
    ativo, pl, ni = _col(d, "ativo_total"), _col(d, "patrimonio_liquido"), _col(d, "lucro_liquido")
    receita = _col(d, "receita_liquida")
    return pd.DataFrame({
        "Fim do período": d["Fim do período"],
        "Ativo total": ativo,
        "Patrimônio líquido": pl,
        "Lucro líquido (LTM)": ni,
        "Receita líquida (LTM)": receita,
        "Provisão p/ perdas (LTM)": _col(d, "provisao"),
        "Despesas não-juros (LTM)": _col(d, "despesa_nao_juros"),
        "Depósitos": _col(d, "depositos"),
        "Dívida (LP + CP)": _col(d, "divida_bruta"),
        "PL/Ativo": _dividir(pl, ativo),
        "ROE (LTM, PL final)": _dividir(ni, pl),
        "ROA (LTM, ativo final)": _dividir(ni, ativo),
        "Índice de eficiência": _dividir(_col(d, "despesa_nao_juros"), receita),
        "Provisão/Receita": _dividir(_col(d, "provisao"), receita),
        "Dívida/PL": _dividir(_col(d, "divida_bruta"), pl),
    })


def _sinal(valor, limites, menor_e_melhor):
    if pd.isna(valor):
        return CINZA
    verde, amarelo = limites
    if menor_e_melhor:
        return VERDE if valor <= verde else AMARELO if valor <= amarelo else VERMELHO
    return VERDE if valor >= verde else AMARELO if valor >= amarelo else VERMELHO


def semaforo_corporativa(linha, perfil="Padrão"):
    """Sinais do periodo mais recente. 'geral' = o pior entre alavancagem e cobertura (os dois
    que mais pesam em credito); cinza se a alavancagem nao pode ser calculada. EBITDA <= 0 com
    dado completo = vermelho."""
    lim = LIMITES.get(perfil, LIMITES["Padrão"])
    alav = _sinal(linha["Dívida líquida/EBITDA"], lim["alavancagem"], True)
    cob = _sinal(linha["Cobertura de juros (EBITDA/juros)"], lim["cobertura"], False)
    liq = _sinal(linha["Liquidez corrente"], lim["liquidez"], False)
    if pd.notna(linha["EBITDA (LTM)"]) and linha["EBITDA (LTM)"] <= 0:
        alav = VERMELHO
    ordem = [VERMELHO, AMARELO, VERDE]
    if alav == CINZA:
        # sem alavancagem (divida em tag propria, EBITDA indisponivel...) nao da pra dizer que
        # esta saudavel so porque a cobertura de juros fecha — fica cinza
        geral = CINZA
    else:
        geral = min((s for s in (alav, cob) if s != CINZA), key=ordem.index)
    fcl = linha["Fluxo de caixa livre (LTM)"]
    return {"geral": geral, "alavancagem": alav, "cobertura": cob, "liquidez": liq,
            "fcl": CINZA if pd.isna(fcl) else (VERDE if fcl > 0 else VERMELHO)}


def tendencia(serie, periodos_atras=4, melhor_se_menor=True, tolerancia=0.25):
    """Compara o periodo mais recente com o de um ano atras (4 trimestres). serie: mais recente
    primeiro. Devolve texto curto ('▼ melhorando (−0.4)', '▲ piorando (+0.6)', '● estável', '—')."""
    if len(serie) <= periodos_atras:
        return "—"
    atual, antes = serie.iloc[0], serie.iloc[periodos_atras]
    if pd.isna(atual) or pd.isna(antes):
        return "—"
    delta = atual - antes
    if abs(delta) < tolerancia:
        return "● estável"
    melhorou = (delta < 0) == melhor_se_menor
    seta = "▼" if delta < 0 else "▲"
    return f"{seta} {'melhorando' if melhorou else 'piorando'} ({delta:+.1f})"


def aviso_defasagem(perfil, bruto, dias_tolerancia=75):
    """Avisa quando os fatos XBRL da SEC estao atras do ultimo 10-K/10-Q arquivado (acontece:
    ex. Citigroup tem 10-Q de 2026 arquivado mas a API so tem ate o 10-K de 2025)."""
    ultimo_arquivado = perfil.get("ultimo_periodo_arquivado")
    if bruto is None or bruto.empty or pd.isna(ultimo_arquivado):
        return None
    ultimo_fatos = bruto["Fim do período"].max()
    if (ultimo_arquivado - ultimo_fatos).days > dias_tolerancia:
        return (f"Os dados XBRL da SEC vão só até {ultimo_fatos:%d/%m/%Y}, mas já há arquivamento "
                f"referente a {ultimo_arquivado:%d/%m/%Y} — os números abaixo estão defasados.")
    return None
