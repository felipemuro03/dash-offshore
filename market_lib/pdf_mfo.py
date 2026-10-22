"""Relatorio 'Evolucao das posicoes' (Fixed Income) no visual do material MFO Revisao de Carteira:
A4 retrato, faixa azul-marinho com logos AVIN | SWM e filete dourado na 1a pagina, cabecalho com
etiqueta MFO nas demais, titulos em Rubik, texto em Montserrat, tabela com cabecalho ardosia e um
grafico de barras por bond. Fontes e logos ficam em assets/ (versionados, pro Streamlit Cloud)."""

import datetime as dt
import re
from io import BytesIO
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

ASSETS = Path(__file__).resolve().parents[1] / "assets"

NAVY = colors.HexColor("#102134")
OURO = colors.HexColor("#896F3D")
OURO_CLARO = colors.HexColor("#B8975A")  # dourado sobre fundo escuro
ARDOSIA = colors.HexColor("#404751")
CLARO = colors.HexColor("#F8F8F6")
CLARO2 = colors.HexColor("#F3F4F6")
LINHA = colors.HexColor("#DADCE0")
TEXTO = colors.HexColor("#2B3340")
MUTED = colors.HexColor("#6B7280")
AZUL = colors.HexColor("#3E5C85")
VERDE = colors.HexColor("#2F6B4F")
VERMELHO = colors.HexColor("#A33A32")

LARGURA, ALTURA = A4
MARGEM = 57.0
LARGURA_UTIL = LARGURA - 2 * MARGEM

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]

_FONTES_OK = False


def _registrar_fontes():
    """Montserrat e Rubik de assets/fonts; se faltar arquivo, cai nas fontes padrao do reportlab."""
    global _FONTES_OK
    if _FONTES_OK:
        return True
    try:
        pasta = ASSETS / "fonts"
        for nome in ("Montserrat-Regular", "Montserrat-SemiBold", "Montserrat-Italic", "Rubik-Medium", "Rubik-Bold"):
            pdfmetrics.registerFont(TTFont(nome, str(pasta / f"{nome}.ttf")))
        pdfmetrics.registerFontFamily("Montserrat-Regular", normal="Montserrat-Regular", bold="Montserrat-SemiBold",
                                      italic="Montserrat-Italic", boldItalic="Montserrat-SemiBold")
        _FONTES_OK = True
    except Exception:  # noqa: BLE001 — sem as fontes o PDF sai com Helvetica, mas sai
        _FONTES_OK = False
    return _FONTES_OK


def _f(nome):
    """Nome da fonte pedida, ou o equivalente padrao se as TTF nao carregaram."""
    if _FONTES_OK:
        return nome
    return {"Montserrat-Regular": "Helvetica", "Montserrat-SemiBold": "Helvetica-Bold", "Montserrat-Italic": "Helvetica-Oblique",
            "Rubik-Medium": "Helvetica-Bold", "Rubik-Bold": "Helvetica-Bold"}[nome]


# ---------------- formatacao (padrao brasileiro, como no material de referencia) ----------------

def br(valor, casas=2):
    if valor is None or pd.isna(valor):
        return "-"
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def br_pct(frac, casas=2, sinal=False):
    if frac is None or pd.isna(frac):
        return "-"
    texto = br(frac * 100, casas) + "%"
    return ("+" + texto) if sinal and frac > 0 else texto


def data_longa(d):
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


# ---------------- logica de resumo ----------------

def resumo_desde_o_inicio(df):
    """Por posicao (identificador), compara o agio/desagio (%) do ULTIMO snapshot com o do PRIMEIRO.
    Devolve (melhoraram, pioraram, iguais, sem_comparacao) — contagens de bonds."""
    chave = "Identificador" if "Identificador" in df.columns else "Descricao"
    melhorou = piorou = iguais = sem_comparacao = 0
    for _, g in df.sort_values("Data").groupby(chave):
        g = g.dropna(subset=["Variacao (%)"])
        if len(g) < 2:
            sem_comparacao += 1
            continue
        dif = g["Variacao (%)"].iloc[-1] - g["Variacao (%)"].iloc[0]
        if dif > 0:
            melhorou += 1
        elif dif < 0:
            piorou += 1
        else:
            iguais += 1
    return melhorou, piorou, iguais, sem_comparacao


def _por_bond(df):
    """Lista de dicts por bond (ordenada pela descricao): serie de snapshots e variacao desde o inicio."""
    chave = "Identificador" if "Identificador" in df.columns else "Descricao"
    saida = []
    for ident, g in df.sort_values("Data").groupby(chave):
        g = g.reset_index(drop=True)
        v = g["Variacao (%)"].dropna()
        saida.append({
            "id": ident, "descricao": _limpar_descricao(g["Descricao"].iloc[-1]),
            "custodia": str(g["Custodia"].iloc[-1]) if "Custodia" in g.columns else "",
            "linhas": g, "desde_inicio": (v.iloc[-1] - v.iloc[0]) if len(v) >= 2 else None,
        })
    return sorted(saida, key=lambda b: b["descricao"])


def _limpar_descricao(descricao):
    """Tira o ruido da descricao do custodiante (codigo ISIN colado, 'CLB CLB' repetido)."""
    texto = re.sub(r"ISIN#\S+\s*", "", str(descricao))
    texto = re.sub(r"\b(CLB)(\s+CLB)+\b", r"\1", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _nome_curto(descricao, limite=46):
    nome = _limpar_descricao(descricao)
    return nome if len(nome) <= limite else nome[: limite - 1].rstrip() + "…"


# ---------------- elementos graficos ----------------

class Kicker(Flowable):
    """Rotulo em caixa-alta dourada com espacamento entre letras (ex.: 'GRAFICO 1', '01 · A CARTEIRA HOJE')."""

    def __init__(self, texto, cor=OURO, tamanho=7.4):
        super().__init__()
        self.texto, self.cor, self.tamanho = texto.upper(), cor, tamanho
        self.width, self.height = LARGURA_UTIL, tamanho + 6

    def wrap(self, w, h):
        return w, self.height

    def draw(self):
        t = self.canv.beginText(0, 3)
        t.setFont(_f("Montserrat-SemiBold"), self.tamanho)
        t.setFillColor(self.cor)
        t.setCharSpace(1.6)
        t.textOut(self.texto)
        t.setCharSpace(0)
        self.canv.drawText(t)


class Filete(Flowable):
    def __init__(self, cor=LINHA, espessura=0.6, espaco=6):
        super().__init__()
        self.cor, self.espessura, self.espaco = cor, espessura, espaco

    def wrap(self, w, h):
        return w, self.espaco * 2

    def draw(self):
        self.canv.setStrokeColor(self.cor)
        self.canv.setLineWidth(self.espessura)
        self.canv.line(0, self.espaco, LARGURA_UTIL, self.espaco)


class GraficoBarras(Flowable):
    """Barras horizontais divergentes (variacao em p.p.), um bond por linha: rotulo | barras | valor."""

    def __init__(self, itens, largura=LARGURA_UTIL):
        super().__init__()
        self.itens, self.largura = itens, largura  # itens: [(rotulo, valor_pp)]
        self.altura_linha = 15
        self.width, self.height = largura, len(itens) * self.altura_linha + 8

    def wrap(self, w, h):
        return self.width, self.height

    def draw(self):
        c = self.canv
        rot_w, val_w = 205, 52
        area = self.largura - rot_w - val_w - 10
        valores = [v for _, v in self.itens]
        lo, hi = min(0, min(valores)), max(0, max(valores))
        amplitude = (hi - lo) or 1
        escala = area / amplitude
        zero = rot_w + 5 + (-lo) * escala
        c.setStrokeColor(LINHA)
        c.setLineWidth(0.5)
        c.line(zero, 0, zero, self.height)
        y = self.height - self.altura_linha
        for rotulo, v in self.itens:
            c.setFont(_f("Montserrat-Regular"), 6.6)
            c.setFillColor(TEXTO)
            c.drawRightString(rot_w, y + 4.5, rotulo)
            x0, x1 = (zero, zero + v * escala) if v >= 0 else (zero + v * escala, zero)
            c.setFillColor(AZUL if v > 0 else OURO)
            c.rect(x0, y + 2, max(x1 - x0, 0.8), 9.5, stroke=0, fill=1)
            c.setFont(_f("Montserrat-SemiBold"), 6.8)
            c.setFillColor(NAVY)
            c.drawRightString(self.largura, y + 4.5, f"{'+' if v > 0 else ''}{br(v)} p.p.")
            y -= self.altura_linha


# ---------------- decoracao de pagina ----------------

def _logo(canvas, nome, x, y_topo, w, h):
    caminho = ASSETS / nome
    if caminho.exists():
        canvas.drawImage(str(caminho), x, ALTURA - y_topo - h, width=w, height=h, mask="auto", preserveAspectRatio=True, anchor="sw")


def _etiqueta_mfo(canvas, x, y, cor_fundo, cor_texto):
    canvas.setFillColor(cor_fundo)
    canvas.rect(x, y, 30, 14, stroke=0, fill=1)
    canvas.setFont(_f("Montserrat-SemiBold"), 7)
    canvas.setFillColor(cor_texto)
    t = canvas.beginText(x + 5.5, y + 4.6)
    t.setFont(_f("Montserrat-SemiBold"), 7)
    t.setCharSpace(1.1)
    t.textOut("MFO")
    t.setCharSpace(0)
    canvas.drawText(t)


def _rodape(canvas, doc, titulo_rodape):
    canvas.setStrokeColor(OURO)
    canvas.setLineWidth(0.5)
    canvas.line(MARGEM, 50, LARGURA - MARGEM, 50)
    canvas.setFont(_f("Montserrat-Regular"), 6.8)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGEM, 37, "SWM MFO")
    canvas.drawString(MARGEM + 48, 37, titulo_rodape)
    canvas.drawRightString(LARGURA - MARGEM, 37, f"Página {doc.page}")


def _primeira_pagina(canvas, doc, rotulo_direita, titulo_rodape):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, ALTURA - 102, LARGURA, 102, stroke=0, fill=1)
    canvas.setFillColor(OURO)
    canvas.rect(0, ALTURA - 106, LARGURA, 4, stroke=0, fill=1)
    _logo(canvas, "logo_avin_claro.png", 57, 33, 96, 35)
    canvas.setStrokeColor(colors.Color(1, 1, 1, alpha=0.45))
    canvas.setLineWidth(0.6)
    canvas.line(168, ALTURA - 38, 168, ALTURA - 70)
    _logo(canvas, "logo_swm_claro.png", 184, 35, 69, 32)

    # etiqueta MFO + rotulo (dourado, espacado) + data, alinhados a direita
    fonte, tam, esp = _f("Montserrat-SemiBold"), 7.6, 1.7
    texto = rotulo_direita.upper()
    larg_texto = stringWidth(texto, fonte, tam) + esp * len(texto)
    x_texto = LARGURA - MARGEM - larg_texto
    _etiqueta_mfo(canvas, x_texto - 38, ALTURA - 50, ARDOSIA, colors.white)
    t = canvas.beginText(x_texto, ALTURA - 45.6)
    t.setFont(fonte, tam)
    t.setFillColor(OURO_CLARO)
    t.setCharSpace(esp)
    t.textOut(texto)
    t.setCharSpace(0)
    canvas.drawText(t)
    canvas.setFont(_f("Montserrat-Regular"), 7.8)
    canvas.setFillColor(colors.white)
    canvas.drawRightString(LARGURA - MARGEM, ALTURA - 64, data_longa(dt.date.today()))
    _rodape(canvas, doc, titulo_rodape)
    canvas.restoreState()


def _paginas_internas(canvas, doc, subtitulo, titulo_rodape):
    canvas.saveState()
    canvas.setFillColor(ARDOSIA)
    canvas.rect(0, ALTURA - 4, LARGURA, 4, stroke=0, fill=1)
    _etiqueta_mfo(canvas, MARGEM, ALTURA - 40, ARDOSIA, colors.white)
    canvas.setFont(_f("Montserrat-Regular"), 8)
    canvas.setFillColor(ARDOSIA)
    canvas.drawString(MARGEM + 38, ALTURA - 36, "|")
    canvas.drawString(MARGEM + 44, ALTURA - 36, subtitulo)
    _logo(canvas, "logo_swm_escuro.png", 428, 26, 38, 18)
    canvas.setStrokeColor(OURO)
    canvas.setLineWidth(0.5)
    canvas.line(474, ALTURA - 28, 474, ALTURA - 44)
    _logo(canvas, "logo_avin_escuro.png", 486, 25, 52, 19)
    _rodape(canvas, doc, titulo_rodape)
    canvas.restoreState()


# ---------------- relatorio ----------------

def _estilos():
    return {
        "titulo": ParagraphStyle("t", fontName=_f("Rubik-Bold"), fontSize=25, leading=29, textColor=NAVY, spaceAfter=6),
        "subtitulo": ParagraphStyle("st", fontName=_f("Montserrat-Regular"), fontSize=11, leading=15, textColor=OURO, spaceAfter=8),
        "corpo": ParagraphStyle("c", fontName=_f("Montserrat-Regular"), fontSize=9.4, leading=14.6, textColor=TEXTO, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName=_f("Rubik-Bold"), fontSize=17.5, leading=21, textColor=NAVY, spaceAfter=2),
        "graf_titulo": ParagraphStyle("gt", fontName=_f("Montserrat-SemiBold"), fontSize=9.6, leading=12, textColor=NAVY),
        "graf_sub": ParagraphStyle("gs", fontName=_f("Montserrat-Italic"), fontSize=7.9, leading=10, textColor=MUTED, spaceAfter=6),
        "fonte": ParagraphStyle("f", fontName=_f("Montserrat-Regular"), fontSize=6.9, leading=9, textColor=MUTED, spaceBefore=4),
        "rotulo_card": ParagraphStyle("rc", fontName=_f("Montserrat-Regular"), fontSize=6.4, leading=8, textColor=MUTED),
        "valor_card": ParagraphStyle("vc", fontName=_f("Rubik-Medium"), fontSize=15, leading=18, textColor=NAVY),
        "rotulo_card_d": ParagraphStyle("rcd", fontName=_f("Montserrat-Regular"), fontSize=6.4, leading=8, textColor=colors.Color(1, 1, 1, alpha=0.8)),
        "valor_card_d": ParagraphStyle("vcd", fontName=_f("Rubik-Medium"), fontSize=15, leading=18, textColor=colors.white),
        "cel": ParagraphStyle("cel", fontName=_f("Montserrat-Regular"), fontSize=7, leading=9, textColor=TEXTO),
        "cel_dir": ParagraphStyle("celd", fontName=_f("Montserrat-Regular"), fontSize=7, leading=9, textColor=TEXTO, alignment=2),
        "cab": ParagraphStyle("cab", fontName=_f("Montserrat-SemiBold"), fontSize=6.8, leading=8.5, textColor=colors.white),
        "cab_dir": ParagraphStyle("cabd", fontName=_f("Montserrat-SemiBold"), fontSize=6.8, leading=8.5, textColor=colors.white, alignment=2),
        "grupo": ParagraphStyle("gr", fontName=_f("Montserrat-SemiBold"), fontSize=7.4, leading=9.5, textColor=NAVY),
        "grupo_dir": ParagraphStyle("grd", fontName=_f("Montserrat-SemiBold"), fontSize=7.2, leading=9.5, textColor=NAVY, alignment=2),
    }


def _cartao(rotulo, valor, destaque, largura, st):
    t = Table([[Paragraph(rotulo.upper(), st["rotulo_card_d" if destaque else "rotulo_card"])],
               [Paragraph(valor, st["valor_card_d" if destaque else "valor_card"])]], colWidths=[largura])
    estilo = [("BACKGROUND", (0, 0), (-1, -1), NAVY if destaque else CLARO2),
              ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
              ("TOPPADDING", (0, 0), (0, 0), 8), ("BOTTOMPADDING", (0, 0), (0, 0), 1),
              ("TOPPADDING", (0, 1), (0, 1), 1), ("BOTTOMPADDING", (0, 1), (0, 1), 9)]
    if not destaque:
        estilo.append(("LINEABOVE", (0, 0), (-1, 0), 2, OURO))
    t.setStyle(TableStyle(estilo))
    return t


def _grade_cartoes(cards, st):
    larg = LARGURA_UTIL / len(cards)
    grade = Table([[_cartao(r, v, d, larg - 4, st) for r, v, d in cards]], colWidths=[larg] * len(cards))
    grade.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                               ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return grade


def _seta(tendencia):
    """Triangulo (ZapfDingbats) + palavra, colorido; vazio de seta quando nao ha comparacao."""
    t = str(tendencia)
    if t.startswith("▲"):
        return f'<font color="{VERDE.hexval()}">Melhorou</font>'
    if t.startswith("▼"):
        return f'<font color="{VERMELHO.hexval()}">Piorou</font>'
    if t.startswith("●"):
        return "Igual"
    return f'<font color="{MUTED.hexval()}">primeiro registro</font>'


def _tabela_historico(bonds, st):
    cab = ["Data", "Preço", "Valor atual (US$)", "Variação (US$)", "Variação (%)", "Tendência"]
    larguras = [60, 50, 92, 92, 82, 105.9]
    dados = [[Paragraph(c, st["cab"] if i == 0 else st["cab_dir"] if i < 5 else st["cab"]) for i, c in enumerate(cab)]]
    estilo = [("BACKGROUND", (0, 0), (-1, 0), ARDOSIA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 3.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
              ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
              ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINHA)]
    for b in bonds:
        linha_grupo = len(dados)
        di = b["desde_inicio"]
        if di is None:
            resumo = f'<font color="{MUTED.hexval()}">um único registro</font>'
        else:
            cor = VERDE if di > 0 else VERMELHO if di < 0 else MUTED
            resumo = f'Desde o início: <font color="{cor.hexval()}">{("+" if di > 0 else "")}{br(di * 100)} p.p.</font>'
        etiqueta = f'<font name="{_f("Montserrat-Regular")}" size="6.4" color="{MUTED.hexval()}">&nbsp;&nbsp;{b["custodia"]} · {b["id"]}</font>'
        dados.append([Paragraph(f"{b['descricao']}{etiqueta}", st["grupo"]), "", "", Paragraph(resumo, st["grupo_dir"]), "", ""])
        estilo += [("SPAN", (0, linha_grupo), (2, linha_grupo)), ("SPAN", (3, linha_grupo), (5, linha_grupo)),
                   ("BACKGROUND", (0, linha_grupo), (-1, linha_grupo), CLARO2),
                   ("LINEABOVE", (0, linha_grupo), (-1, linha_grupo), 0.6, OURO)]
        for _, r in b["linhas"].iterrows():
            v_us = r["Variacao (US$)"]
            cor = VERMELHO if v_us < 0 else VERDE if v_us > 0 else TEXTO
            fmt = lambda x, c=cor: f'<font color="{c.hexval()}">{x}</font>'  # noqa: E731
            dados.append([
                Paragraph(pd.to_datetime(r["Data"]).strftime("%d/%m/%Y"), st["cel"]),
                Paragraph(br(r["Preco"], 3) if pd.notna(r["Preco"]) else "-", st["cel_dir"]),
                Paragraph(br(r["Valor Atual (US$)"]), st["cel_dir"]),
                Paragraph(fmt(br(v_us)), st["cel_dir"]),
                Paragraph(fmt(br_pct(r["Variacao (%)"])), st["cel_dir"]),
                Paragraph(_seta(r["Tendência"]), st["cel"]),
            ])
    tabela = Table(dados, colWidths=larguras, repeatRows=1)
    tabela.setStyle(TableStyle(estilo))
    return tabela


def gerar_pdf_evolucao_mfo(df, cliente):
    """df: evolucao das posicoes de 1 cliente, com a coluna 'Tendência' (snapshot a snapshot). Devolve bytes do PDF."""
    _registrar_fontes()
    st = _estilos()
    titulo_rodape = f"Evolução de Posições — {cliente}"
    buffer = BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM, topMargin=60, bottomMargin=62,
                          title=f"Evolução das posições — {cliente}", author="SWM MFO")
    frame_1 = Frame(MARGEM, 62, LARGURA_UTIL, ALTURA - 106 - 24 - 62, id="f1", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    frame_n = Frame(MARGEM, 62, LARGURA_UTIL, ALTURA - 62 - 62, id="fn", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="primeira", frames=[frame_1], onPage=lambda c, d: _primeira_pagina(c, d, "Evolução de posições", titulo_rodape)),
        PageTemplate(id="internas", frames=[frame_n], onPage=lambda c, d: _paginas_internas(c, d, "Evolução de Posições", titulo_rodape)),
    ])

    bonds = _por_bond(df)
    datas = sorted(pd.to_datetime(df["Data"]).unique())
    d0, d1 = pd.Timestamp(datas[0]), pd.Timestamp(datas[-1])
    n_bonds, n_snap = len(bonds), len(datas)
    melhorou, piorou, iguais, sem_comp = resumo_desde_o_inicio(df)

    # posicao no ultimo snapshot (so bonds que ainda estao na carteira)
    ult = df[pd.to_datetime(df["Data"]) == d1]
    valor_hoje = ult["Valor Atual (US$)"].sum()
    var_hoje = ult["Variacao (US$)"].sum()
    custo_hoje = valor_hoje - var_hoje
    pct_hoje = var_hoje / custo_hoje if custo_hoje else None

    def pl(n, singular, plural):
        return singular if n == 1 else plural

    corpo = (f"Acompanhamos <b>{n_bonds} {pl(n_bonds, 'bond', 'bonds')}</b> da carteira em <b>{n_snap} {pl(n_snap, 'snapshot', 'snapshots')}</b>, "
             f"de {d0:%d/%m/%Y} a {d1:%d/%m/%Y}. Desde o primeiro registro, <b>{melhorou} {pl(melhorou, 'melhorou', 'melhoraram')}</b> e "
             f"<b>{piorou} {pl(piorou, 'piorou', 'pioraram')}</b> em relação ao que foi pago (ágio/deságio sobre o custo). Na última foto, "
             f"{pl(len(ult), 'a posição soma', 'as ' + str(len(ult)) + ' posições somam')} <b>US$ {br(valor_hoje)}</b>, com ágio/deságio "
             f"de <b>US$ {br(var_hoje)}</b>" + (f" ({br_pct(pct_hoje, 2, True)})." if pct_hoje is not None else "."))

    cards = [("Posições acompanhadas", str(n_bonds), False), ("Snapshots no período", str(n_snap), False),
             ("Melhoraram desde o início", str(melhorou), False), ("Pioraram desde o início", str(piorou), True)]
    extras = []
    if iguais:
        extras.append(f"{iguais} sem variação")
    if sem_comp:
        extras.append(f"{sem_comp} com um único registro (sem comparação)")

    # grafico: variacao desde o inicio por bond (no maximo 24 barras: 12 maiores quedas + 12 maiores altas)
    barras = sorted([(_nome_curto(b["descricao"]), b["desde_inicio"] * 100) for b in bonds if b["desde_inicio"] is not None],
                    key=lambda x: -x[1])
    nota_corte = ""
    if len(barras) > 24:
        barras = barras[:12] + barras[-12:]
        nota_corte = " Exibidas as 12 maiores altas e as 12 maiores quedas."

    elementos = [
        Paragraph("Evolução dos bonds desde o primeiro registro", st["titulo"]),
        Paragraph(f"{cliente}", st["subtitulo"]),
        Filete(),
        Paragraph(corpo, st["corpo"]),
        Spacer(1, 6),
        _grade_cartoes(cards, st),
        Paragraph("Melhoraram / pioraram: por posição, o ágio/deságio (%) do último snapshot contra o do primeiro snapshot daquela posição "
                  "(contagem de bonds, não de comparações)." + (f" Fora da contagem: {'; '.join(extras)}." if extras else "") +
                  " Na tabela das páginas seguintes, a coluna Tendência compara cada snapshot com o anterior da mesma posição (nunca entre bonds "
                  "diferentes) e ‘Desde o início’ compara o último snapshot com o primeiro. Variação = valor atual − valor de compra. "
                  "Rentabilidade passada não é garantia de rentabilidade futura.", st["fonte"]),
        Spacer(1, 12),
    ]
    if barras:
        elementos += [KeepTogether([
            Kicker("Gráfico 1"),
            Paragraph("Variação do ágio/deságio desde o primeiro registro", st["graf_titulo"]),
            Paragraph("Pontos percentuais (último snapshot menos o primeiro), por bond.", st["graf_sub"]),
            GraficoBarras(barras),
            Paragraph(f"Fonte: SWM MFO, posições salvas entre {d0:%d/%m/%Y} e {d1:%d/%m/%Y}. Azul = melhorou; dourado = piorou. "
                      f"Não inclui juros/cupons recebidos, só a marcação do ativo.{nota_corte}", st["fonte"]),
        ])]
    elementos += [
        NextPageTemplate("internas"),
        PageBreak(),
        Kicker("01 · Histórico por posição"),
        Paragraph("Snapshot a snapshot", st["h2"]),
        Filete(OURO, 0.5, 5),
        Spacer(1, 4),
        _tabela_historico(bonds, st),
    ]
    doc.build(elementos)
    return buffer.getvalue()
