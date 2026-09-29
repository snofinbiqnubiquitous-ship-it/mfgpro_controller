"""Build all manual copies from docs Markdown. Requires reportlab and Meiryo."""
from pathlib import Path
import argparse
import html
import re
import shutil
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
NAME = 'QAD_99_7_1_1_Order_Entry_Manual'

def build(font):
    pdfmetrics.registerFont(TTFont('Japanese', str(font), subfontIndex=0))
    source = ROOT / 'docs' / (NAME + '.md')
    lines = source.read_text(encoding='utf-8-sig').splitlines()
    styles = {
        'body': ParagraphStyle('body', fontName='Japanese', fontSize=9, leading=15, spaceAfter=7, wordWrap='CJK'),
        'h1': ParagraphStyle('h1', fontName='Japanese', fontSize=19, leading=28, spaceAfter=18, wordWrap='CJK'),
        'h2': ParagraphStyle('h2', fontName='Japanese', fontSize=13, leading=20, spaceBefore=15, spaceAfter=9, keepWithNext=True, wordWrap='CJK'),
        'h3': ParagraphStyle('h3', fontName='Japanese', fontSize=10.5, leading=17, spaceBefore=10, spaceAfter=6, keepWithNext=True, wordWrap='CJK'),
        'code': ParagraphStyle('code', fontName='Japanese', fontSize=7.3, leading=12, spaceAfter=4, wordWrap='CJK'),
        'cell': ParagraphStyle('cell', fontName='Japanese', fontSize=8, leading=13, wordWrap='CJK'),
    }
    story, markup = [], []
    width = A4[0] - 88
    i = 0
    def paragraph(text, style='body'):
        return Paragraph(html.escape(text), styles[style])
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if line.startswith('```'):
            code = []
            while i < len(lines) and not lines[i].startswith('```'):
                code.append(lines[i]); i += 1
            i += 1
            for row in code:
                story.append(paragraph(row, 'code'))
            story.append(Spacer(1, 7))
            markup.append('<pre>' + html.escape('\n'.join(code)) + '</pre>')
        elif line.startswith('|'):
            rows = [line]
            while i < len(lines) and lines[i].startswith('|'):
                rows.append(lines[i]); i += 1
            cells = [[c.strip() for c in row.strip('|').split('|')] for row in rows if not re.match(r'^\|[\s:|\-]+$', row)]
            fractions = [0.10, 0.39, 0.51] if cells[0][0] in ('番号', '順番') else ([0.25, 0.75] if len(cells[0]) == 2 else [1 / len(cells[0])] * len(cells[0]))
            table = Table([[paragraph(c, 'cell') for c in row] for row in cells], colWidths=[width*f for f in fractions], repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9eff3')),
                ('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LINEBELOW',(0,0),(-1,-1),0.35,colors.HexColor('#d6dfe4')),
                ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
                ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
            ]))
            story.extend([table, Spacer(1,10)])
            markup.append('<table>' + ''.join('<tr>' + ''.join('<td>' + html.escape(c) + '</td>' for c in row) + '</tr>' for row in cells) + '</table>')
        else:
            match = re.match(r'^(#{1,3}) (.*)', line)
            style, content = ('h'+str(len(match[1])), match[2]) if match else ('body', line)
            story.append(paragraph(content, style))
            tag = style if style.startswith('h') else 'p'
            markup.append(f'<{tag}>{html.escape(content)}</{tag}>')
    def footer(canvas, doc):
        canvas.setFont('Japanese', 8)
        canvas.setFillColor(colors.HexColor('#657582'))
        canvas.drawString(44, 25, 'QAD 99.7.1.1 | 2026-09-29')
        canvas.drawRightString(A4[0]-44, 25, str(doc.page))
    target = source.with_suffix('.pdf')
    SimpleDocTemplate(str(target), pagesize=A4, rightMargin=44, leftMargin=44, topMargin=40, bottomMargin=46, title='QAD 99.7.1.1 受注入力 操作・自動化仕様マニュアル', author='').build(story, onFirstPage=footer, onLaterPages=footer)
    css = 'body{font-family:Meiryo,sans-serif;color:#22303b;max-width:900px;margin:40px auto;line-height:1.8}h1{font-size:26px}h2{font-size:20px;margin-top:30px}h3{font-size:16px}table{border-collapse:collapse;width:100%;font-size:13px}td{padding:8px;border-bottom:1px solid #d6dfe4;vertical-align:top}tr:first-child{background:#e9eff3}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}p{overflow-wrap:anywhere}@media print{body{margin:0}h1,h2,h3{break-after:avoid}tr{break-inside:avoid}}'
    (source.parent/'manual_print.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><title>QAD 受注入力マニュアル</title><style>'+css+'</style><body>'+'\n'.join(markup)+'</body></html>', encoding='utf-8')
    shutil.copyfile(source, ROOT/source.name)
    shutil.copyfile(target, ROOT/target.name)
    print(target)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/meiryo.ttc'))
    build(parser.parse_args().font)
