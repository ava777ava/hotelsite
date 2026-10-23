import json, re, sys
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Preformatted, ListFlowable, ListItem
from xml.sax.saxutils import escape

F = '/usr/share/fonts/truetype/liberation/'
pdfmetrics.registerFont(TTFont('LS', F + 'LiberationSans-Regular.ttf'))
pdfmetrics.registerFont(TTFont('LS-B', F + 'LiberationSans-Bold.ttf'))
pdfmetrics.registerFont(TTFont('LS-I', F + 'LiberationSans-Italic.ttf'))
pdfmetrics.registerFont(TTFont('LS-BI', F + 'LiberationSans-BoldItalic.ttf'))
pdfmetrics.registerFont(TTFont('LM', F + 'LiberationMono-Regular.ttf'))
pdfmetrics.registerFont(TTFont('LM-B', F + 'LiberationMono-Bold.ttf'))
pdfmetrics.registerFontFamily('LS', normal='LS', bold='LS-B', italic='LS-I', boldItalic='LS-BI')
pdfmetrics.registerFontFamily('LM', normal='LM', bold='LM-B', italic='LM', boldItalic='LM-B')
pdfmetrics.registerFont(TTFont('DJ', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))

GREEN = colors.HexColor('#2F5D50'); INK = colors.HexColor('#1C2420'); GREY = colors.HexColor('#5B6559'); OCHRE = colors.HexColor('#B7791F')
W, H = A4; M = 20 * mm; CW = W - 2 * M

body = ParagraphStyle('body', fontName='LS', fontSize=10.5, leading=15, textColor=INK, spaceAfter=5, alignment=TA_LEFT)
small = ParagraphStyle('small', parent=body, fontSize=10, leading=13.5, spaceAfter=0)
h1s = ParagraphStyle('h1', parent=body, fontName='LS-B', fontSize=20, leading=25, textColor=GREEN, spaceAfter=12)
h2s = ParagraphStyle('h2', parent=body, fontName='LS-B', fontSize=13.5, leading=18, spaceBefore=12, spaceAfter=6, keepWithNext=1)
h3s = ParagraphStyle('h3', parent=body, fontName='LS-B', fontSize=11.5, leading=15, textColor=GREEN, spaceBefore=8, spaceAfter=4, keepWithNext=1)
codes = ParagraphStyle('code', fontName='LM', fontSize=8.6, leading=11.5, textColor=INK)

def markup(t):
    t = escape(t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', t)
    t = re.sub(r'`([^`]+)`', r'<font name="LM" size="9" color="#8A2D12">\1</font>', t)
    return t

def P(t, st=body): return Paragraph(markup(t), st)

def box(fill, edge, title, lines):
    inner = [Paragraph(f'<font color="{edge}"><b>{escape(title)}</b></font>', small)] + [Paragraph(markup(l), ParagraphStyle('bx', parent=small, spaceBefore=3)) for l in lines]
    t = Table([[inner]], colWidths=[CW])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(fill)), ('LINEBEFORE', (0, 0), (0, -1), 3, colors.HexColor(edge)),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
    return KeepTogether([t, Spacer(1, 8)])

def code(text):
    # длинные строки переносим по ширине
    lines = []
    maxc = 96
    for l in text.split('\n'):
        while len(l) > maxc:
            lines.append(l[:maxc]); l = '    ' + l[maxc:]
        lines.append(l)
    pre = Preformatted('\n'.join(lines), codes)
    t = Table([[pre]], colWidths=[CW])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F1F3EE')), ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#D8DDD1')),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    return [t, Spacer(1, 8)]

def table(widths, header, rows):
    tot = sum(widths); ws = [w / tot * CW for w in widths]
    hs = ParagraphStyle('th', parent=small, fontName='LS-B', textColor=colors.white, fontSize=9.5, leading=12)
    cs = ParagraphStyle('td', parent=small, fontSize=9.5, leading=12.5)
    data = [[Paragraph(markup(h), hs) for h in header]] + [[Paragraph(markup(c).replace('\n', '<br/>'), cs) for c in r] for r in rows]
    t = Table(data, colWidths=ws, repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), GREEN), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D8DDD1')), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7F8F4')]), ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    return [t, Spacer(1, 8)]

def numbered(items):
    return [ListFlowable([ListItem(P(t), leftIndent=18) for t in items], bulletType='1', bulletFormat='%s.', bulletFontName='LS-B', bulletFontSize=10.5, leftIndent=18), Spacer(1, 4)]
def bullets(items):
    return [ListFlowable([ListItem(P(t), leftIndent=16) for t in items], bulletType='bullet', start='•', bulletFontName='LS', leftIndent=16), Spacer(1, 4)]
def checks(items):
    rows = [[Paragraph('<font name="DJ" size="12">☐</font>', small), P(t)] for t in items]
    t = Table(rows, colWidths=[16, CW - 16])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 2), ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
    return [t, Spacer(1, 6)]

def cover():
    s = lambda **k: ParagraphStyle('c', parent=body, **k)
    return [Spacer(1, 70 * mm), Paragraph('<font color="#B7791F"><b>Ф Л И Г Е Л Ь</b></font>', s(fontSize=14, leading=18, spaceAfter=8)),
        Paragraph('<font color="#2F5D50"><b>Полный туториал по запуску сервиса</b></font>', s(fontSize=30, leading=36, spaceAfter=14)),
        Paragraph('От покупки сервера до первого клиента: пошагово, простыми словами, с командами «копируй и вставляй»', s(fontSize=14, leading=19, textColor=GREY, spaceAfter=30)),
        Paragraph('Для кого: для владельца сервиса, который раньше не разворачивал серверы.', s(fontSize=12, leading=16, spaceAfter=5)),
        Paragraph('Сколько времени: первый запуск — 2–3 часа, подключение первой площадки — ещё полдня (из-за ожидания обмена календарями).', s(fontSize=12, leading=16, spaceAfter=5)),
        Paragraph('Версия документа: 23.10.2026 · ветка проекта main', s(fontSize=12, leading=16, textColor=GREY))]

content = json.load(open('content.json'))
story = []
first_h1 = True
for kind, *a in content:
    if kind == 'cover': story += cover()
    elif kind == 'h1':
        story += [PageBreak(), Paragraph(markup(a[0]), h1s)]
    elif kind == 'h2': story.append(P(a[0], h2s))
    elif kind == 'h3': story.append(P(a[0], h3s))
    elif kind == 'p': story.append(P(a[0]))
    elif kind == 'b': story += bullets(a[0])
    elif kind == 'n': story += numbered(a[0])
    elif kind == 'c': story += checks(a[0])
    elif kind == 'code': story += code(a[0])
    elif kind == 'tip': story.append(box('#E6F1EC', '#2F5D50', a[0], a[1]))
    elif kind == 'warn': story.append(box('#FBEFD9', '#B7791F', a[0], a[1]))
    elif kind == 'danger': story.append(box('#F8E3DA', '#B4562E', a[0], a[1]))
    elif kind == 'table': story += table(a[0], a[1], a[2])
    else: raise SystemExit('unknown ' + kind)

def footer(c, d):
    c.saveState(); c.setFont('LS', 8.5); c.setFillColor(GREY)
    if d.page > 1:
        c.drawString(M, 12 * mm, 'Флигель — туториал по запуску'); c.drawRightString(W - M, 12 * mm, str(d.page))
    c.restoreState()

doc = BaseDocTemplate(sys.argv[1], pagesize=A4, leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=22 * mm, title='Флигель — туториал по запуску', author='Флигель')
doc.addPageTemplates([PageTemplate(id='p', frames=[Frame(M, 22 * mm, CW, H - M - 22 * mm, id='f', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=footer)])
doc.build(story)
print('ok')
