"""Geracao de PDF da posicao de bonds — mesmo estilo visual (dourado/preto, logo SWM,
cards de metricas) do relatorio de RV usado no Dash Onshore, adaptado pra Fixed Income."""

import datetime as dt
from io import BytesIO
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "logo_swm.png"

OURO = colors.Color(201 / 255, 162 / 255, 39 / 255)
PRETO = colors.Color(26 / 255, 26 / 255, 26 / 255)
CINZA = colors.Color(120 / 255, 120 / 255, 120 / 255)
CLARO = colors.Color(246 / 255, 246 / 255, 244 / 255)
VERDE = colors.Color(27 / 255, 122 / 255, 61 / 255)
VERMELHO = colors.Color(179 / 255, 38 / 255, 30 / 255)
BRANCO = colors.white

_ESTILO_TITULO = ParagraphStyle("TituloBonds", fontName="Helvetica-Bold", fontSize=13, textColor=PRETO, spaceAfter=3)
_ESTILO_SUB = ParagraphStyle("SubBonds", fontName="Helvetica", fontSize=9.5, textColor=CINZA, spaceAfter=10)
_ESTILO_SECAO = ParagraphStyle("SecaoBonds", fontName="Helvetica-Bold", fontSize=10.5, textColor=PRETO, spaceBefore=10, spaceAfter=4)
_ESTILO_RODAPE = ParagraphStyle("RodapeBonds", fontName="Helvetica-Oblique", fontSize=7.5, textColor=CINZA)

_ESTILO_ROTULO_CARD = ParagraphStyle("RotuloCard", fontName="Helvetica", fontSize=7.5, textColor=CINZA, leading=9)
_ESTILO_VALOR_CARD = ParagraphStyle("ValorCard", fontName="Helvetica-Bold", fontSize=13, textColor=PRETO, leading=15)
_ESTILO_ROTULO_CARD_D = ParagraphStyle("RotuloCardD", parent=_ESTILO_ROTULO_CARD, textColor=BRANCO)
_ESTILO_VALOR_CARD_D = ParagraphStyle("ValorCardD", parent=_ESTILO_VALOR_CARD, textColor=BRANCO)

_ESTILO_DESC = ParagraphStyle("DescCelulaBonds", fontName="Helvetica", fontSize=7.5, leading=9)

CABECALHO = [
    "Custódia", "Ativo", "Preço", "Valor Atual (US$)", "Valor Compra (US$)",
    "Ágio/Deságio (US$)", "Variação (%)",
]


def _card(rotulo, valor, destaque=False, largura=4.6 * cm):
    estilo_rotulo = _ESTILO_ROTULO_CARD_D if destaque else _ESTILO_ROTULO_CARD
    estilo_valor = _ESTILO_VALOR_CARD_D if destaque else _ESTILO_VALOR_CARD
    tabela = Table(
        [[Paragraph(rotulo.upper(), estilo_rotulo)], [Paragraph(valor, estilo_valor)]],
        colWidths=[largura],
    )
    estilo = [
        ("BACKGROUND", (0, 0), (-1, -1), OURO if destaque else CLARO),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (0, 0), 6),
        ("BOTTOMPADDING", (0, 0), (0, 0), 1),
        ("TOPPADDING", (0, 1), (0, 1), 1),
        ("BOTTOMPADDING", (0, 1), (0, 1), 7),
    ]
    if not destaque:
        estilo.append(("LINEABOVE", (0, 0), (-1, 0), 2, OURO))
    tabela.setStyle(TableStyle(estilo))
    return tabela


def _grade_cards(cards, por_linha, largura_total):
    largura_card = largura_total / por_linha
    linhas, linha_atual = [], []
    for rotulo, valor, destaque in cards:
        linha_atual.append(_card(rotulo, valor, destaque, largura=largura_card))
        if len(linha_atual) == por_linha:
            linhas.append(linha_atual)
            linha_atual = []
    if linha_atual:
        while len(linha_atual) < por_linha:
            linha_atual.append("")
        linhas.append(linha_atual)
    grade = Table(linhas, colWidths=[largura_card] * por_linha)
    grade.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return grade


def _formatar_linhas(df):
    linhas = [CABECALHO]
    for _, row in df.iterrows():
        preco = f"{row['Preco']:.3f}" if pd.notna(row["Preco"]) else "-"
        variacao_pct = f"{row['Variacao (%)']:.2%}" if pd.notna(row["Variacao (%)"]) else "-"
        linhas.append([
            row["Custodia"],
            Paragraph(str(row["Descricao"]), _ESTILO_DESC),
            preco,
            f"{row['Valor Atual (US$)']:,.2f}",
            f"{row['Valor Compra (US$)']:,.2f}",
            f"{row['Variacao (US$)']:,.2f}",
            variacao_pct,
        ])
    return linhas


def _montar_tabela(df):
    dados = _formatar_linhas(df)
    tabela = Table(
        dados,
        colWidths=[2 * cm, 6.6 * cm, 1.8 * cm, 2.8 * cm, 2.8 * cm, 2.8 * cm, 2.2 * cm],
        repeatRows=1,
    )
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), PRETO),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRANCO),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CLARO]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        cor = VERMELHO if row["Variacao (US$)"] < 0 else VERDE
        estilo.append(("TEXTCOLOR", (5, i), (6, i), cor))
    tabela.setStyle(TableStyle(estilo))
    return tabela


def _montar_documento(subtitulo, rodape_cliente):
    """Doc + callback de cabecalho/rodape compartilhados pelos relatorios de bonds."""
    buffer = BytesIO()
    largura_pagina, altura_pagina = landscape(A4)
    margem_lateral = 1.5 * cm

    def _cabecalho_rodape(canvas, doc):
        canvas.saveState()
        if LOGO_PATH.exists():
            canvas.drawImage(
                str(LOGO_PATH), margem_lateral, altura_pagina - 2.15 * cm,
                width=1.7 * cm, height=1.7 * cm, mask="auto", preserveAspectRatio=True,
            )
        canvas.setFont("Helvetica-Bold", 15)
        canvas.setFillColor(PRETO)
        canvas.drawString(margem_lateral + 2.1 * cm, altura_pagina - 1.55 * cm, "SWM MFO")
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(CINZA)
        canvas.drawString(margem_lateral + 2.1 * cm, altura_pagina - 2.05 * cm, subtitulo)
        canvas.setStrokeColor(OURO)
        canvas.setLineWidth(1.3)
        canvas.line(margem_lateral, altura_pagina - 2.35 * cm, largura_pagina - margem_lateral, altura_pagina - 2.35 * cm)

        canvas.setStrokeColor(OURO)
        canvas.setLineWidth(0.5)
        canvas.line(margem_lateral, 1.5 * cm, largura_pagina - margem_lateral, 1.5 * cm)
        canvas.setFont("Helvetica-Oblique", 7.5)
        canvas.setFillColor(CINZA)
        canvas.drawString(margem_lateral, 1.1 * cm, f"{rodape_cliente}  |  Confidencial")
        canvas.drawRightString(largura_pagina - margem_lateral, 1.1 * cm, f"Página {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        topMargin=2.9 * cm, bottomMargin=2 * cm, leftMargin=margem_lateral, rightMargin=margem_lateral,
    )
    return buffer, doc, _cabecalho_rodape


def gerar_pdf_posicao(df, titulo, data_snapshot=None):
    """df: linhas ja filtradas (posicoes de 1 cliente, ou de todos, pra uso interno)."""
    buffer, doc, _cabecalho_rodape = _montar_documento(
        "Relatório de Posição — Fixed Income (Bonds)", f"Cliente: {titulo}"
    )

    data_str = data_snapshot or dt.date.today().strftime("%d/%m/%Y")
    valor_atual_total = df["Valor Atual (US$)"].sum()
    valor_compra_total = df["Valor Compra (US$)"].sum()
    variacao_total = valor_atual_total - valor_compra_total
    variacao_pct_total = variacao_total / valor_compra_total if valor_compra_total else 0

    cards = [
        ("Valor Atual Total", f"US$ {valor_atual_total:,.2f}", False),
        ("Valor de Compra Total", f"US$ {valor_compra_total:,.2f}", False),
        ("Nº de Posições", str(len(df)), False),
        ("Ágio/Deságio Total", f"US$ {variacao_total:,.2f}  ({variacao_pct_total:+.2%})", True),
    ]

    largura_conteudo = doc.width

    elementos = [
        Paragraph(f"Posição de bonds — {titulo}", _ESTILO_TITULO),
        Paragraph(f"Gerado em {data_str}", _ESTILO_SUB),
        _grade_cards(cards, por_linha=4, largura_total=largura_conteudo),
        Spacer(1, 10),
        Paragraph("Detalhe por posição", _ESTILO_SECAO),
        _montar_tabela(df.sort_values("Variacao (%)")),
        Spacer(1, 10),
        Paragraph(
            "Ágio/Deságio (US$) = Valor Atual &minus; Valor de Compra. Não inclui juros/"
            "cupons recebidos ao longo do período, só a marcação do ativo em si.",
            _ESTILO_RODAPE,
        ),
    ]

    doc.build(elementos, onFirstPage=_cabecalho_rodape, onLaterPages=_cabecalho_rodape)
    return buffer.getvalue()


CABECALHO_EVOLUCAO = [
    "Data", "Ativo", "Preço", "Valor Atual (US$)", "Variação (US$)", "Variação (%)", "Tendência",
]


def _formatar_linhas_evolucao(df):
    linhas = [CABECALHO_EVOLUCAO]
    for _, row in df.iterrows():
        preco = f"{row['Preco']:.3f}" if pd.notna(row["Preco"]) else "-"
        variacao_pct = f"{row['Variacao (%)']:.2%}" if pd.notna(row["Variacao (%)"]) else "-"
        data_str = pd.to_datetime(row["Data"]).strftime("%d/%m/%Y")
        linhas.append([
            data_str,
            Paragraph(str(row["Descricao"]), _ESTILO_DESC),
            preco,
            f"{row['Valor Atual (US$)']:,.2f}",
            f"{row['Variacao (US$)']:,.2f}",
            variacao_pct,
            str(row["Tendência"]),
        ])
    return linhas


def _montar_tabela_evolucao(df):
    dados = _formatar_linhas_evolucao(df)
    tabela = Table(
        dados,
        colWidths=[2.2 * cm, 6.4 * cm, 1.8 * cm, 2.8 * cm, 2.6 * cm, 2.2 * cm, 2.9 * cm],
        repeatRows=1,
    )
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), PRETO),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRANCO),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CLARO]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        cor = VERMELHO if row["Variacao (US$)"] < 0 else VERDE
        estilo.append(("TEXTCOLOR", (4, i), (5, i), cor))
        tendencia = str(row["Tendência"])
        if tendencia.startswith("▲"):
            estilo.append(("TEXTCOLOR", (6, i), (6, i), VERDE))
        elif tendencia.startswith("▼"):
            estilo.append(("TEXTCOLOR", (6, i), (6, i), VERMELHO))
    tabela.setStyle(TableStyle(estilo))
    return tabela


def gerar_pdf_evolucao(df, cliente):
    """df: evolucao de todas as posicoes de 1 cliente, ja com a coluna 'Tendência' calculada
    (mesmo formato exibido na tela — colunas Data, Descricao, Preco, Valor Atual (US$),
    Variacao (US$), Variacao (%), Tendência)."""
    buffer, doc, _cabecalho_rodape = _montar_documento(
        "Evolução das Posições — Fixed Income (Bonds)", f"Cliente: {cliente}"
    )

    n_posicoes = df["Descricao"].nunique()
    n_snapshots = df["Data"].nunique()
    n_melhorou = int(df["Tendência"].str.startswith("▲").sum())
    n_piorou = int(df["Tendência"].str.startswith("▼").sum())

    cards = [
        ("Posições Acompanhadas", str(n_posicoes), False),
        ("Snapshots no Período", str(n_snapshots), False),
        ("Melhoraram", str(n_melhorou), False),
        ("Pioraram", str(n_piorou), True),
    ]

    largura_conteudo = doc.width

    elementos = [
        Paragraph(f"Evolução das posições — {cliente}", _ESTILO_TITULO),
        Paragraph(f"Gerado em {dt.date.today().strftime('%d/%m/%Y')}", _ESTILO_SUB),
        _grade_cards(cards, por_linha=4, largura_total=largura_conteudo),
        Spacer(1, 10),
        Paragraph("Histórico por posição", _ESTILO_SECAO),
        _montar_tabela_evolucao(df.sort_values(["Descricao", "Data"])),
        Spacer(1, 10),
        Paragraph(
            "Tendência compara cada posição só com o próprio histórico (não entre bonds "
            "diferentes) — 'primeiro registro' quando só há 1 snapshot salvo pra aquela "
            "posição ainda.",
            _ESTILO_RODAPE,
        ),
    ]

    doc.build(elementos, onFirstPage=_cabecalho_rodape, onLaterPages=_cabecalho_rodape)
    return buffer.getvalue()
