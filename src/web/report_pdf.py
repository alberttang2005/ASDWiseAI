"""Caregiver report PDF in the camera-ready report's visual structure.

The layout follows the example; all clinical content comes from the validated
report object, never from the example's fictional interpretation.
"""
from datetime import datetime
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .domain import QUESTIONS

NAVY = colors.HexColor('#19365c')
BLUE = colors.HexColor('#2d70b8')
INK = colors.HexColor('#25354a')
MUTED = colors.HexColor('#63758c')
LINE = colors.HexColor('#d9e4f0')
PALE = colors.HexColor('#f5f8fc')
AMBER = colors.HexColor('#d89b22')
RED = colors.HexColor('#a63d3d')
GREEN = colors.HexColor('#237a51')


def _styles():
    base = dict(fontName='Helvetica', textColor=INK, allowWidows=0, allowOrphans=0)
    return {
        'title': ParagraphStyle('Title', fontName='Helvetica-Bold', fontSize=16, leading=20, textColor=NAVY, alignment=TA_CENTER),
        'sub': ParagraphStyle('Sub', **base, fontSize=9, leading=13, alignment=TA_CENTER),
        'score': ParagraphStyle('Score', fontName='Helvetica-Bold', fontSize=23, leading=26, textColor=NAVY, alignment=TA_CENTER),
        'band': ParagraphStyle('Band', fontName='Helvetica-Bold', fontSize=9, leading=14, textColor=NAVY, alignment=TA_CENTER),
        'body': ParagraphStyle('Body', **base, fontSize=9, leading=13, spaceAfter=5),
        'small': ParagraphStyle('Small', **base, fontSize=8, leading=11, spaceAfter=3),
        'table': ParagraphStyle('TableText', **base, fontSize=8, leading=10),
        'tableHead': ParagraphStyle('TableHead', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white),
        'section': ParagraphStyle('Section', fontName='Helvetica-Bold', fontSize=11, leading=14, textColor=NAVY, spaceBefore=12, spaceAfter=4),
        'group': ParagraphStyle('Group', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=BLUE, spaceBefore=9, spaceAfter=5, keepWithNext=1),
        'criterion': ParagraphStyle('Criterion', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=NAVY, spaceBefore=7, spaceAfter=3, keepWithNext=1),
        'label': ParagraphStyle('Label', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=NAVY, spaceBefore=7, spaceAfter=3),
        'quote': ParagraphStyle('Quote', **base, fontSize=8.5, leading=12, leftIndent=13, spaceAfter=3),
        'disclaimer': ParagraphStyle('Disclaimer', **base, fontSize=8, leading=11),
    }


def _para(text, style):
    return Paragraph(escape(str(text)).replace('\n', '<br/>'), style)


def _rich(parts, style):
    """Only trusted markup; every dynamic field is escaped first."""
    return Paragraph(''.join(parts), style)


def _section(story, title, styles):
    story.append(KeepTogether([
        _para(title, styles['section']),
        HRFlowable(width='100%', thickness=1.3, color=BLUE, spaceAfter=7),
    ]))


def _date(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).strftime('%B %d, %Y at %I:%M %p')
    except (ValueError, AttributeError):
        return str(value)


def _item_table(items, styles):
    heads = ['#', 'Item', 'Response', 'Result']
    rows = [[_para(label, styles['tableHead']) for label in heads]]
    for item in items:
        answer = str(item['answer']).capitalize()
        result = {'elevated likelihood': 'At Risk', 'low likelihood': 'Pass', 'unresolved': 'Unresolved'}.get(item['result'], item['result'])
        rows.append([_para(item['id'], styles['table']), _para(item['label'], styles['table']), _para(answer, styles['table']), _para(result, styles['table'])])
    table = Table(rows, colWidths=[32, 267, 83, 95], repeatRows=1, hAlign='LEFT')
    commands = [
        ('BACKGROUND', (0, 0), (-1, 0), BLUE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, 1), (-1, -1), .35, LINE),
    ]
    for row, item in enumerate(items, 1):
        commands.append(('BACKGROUND', (0, row), (-1, row), colors.HexColor('#fff1f0') if item['result'] == 'elevated likelihood' else PALE if row % 2 else colors.white))
        commands.append(('TEXTCOLOR', (3, row), (3, row), RED if item['result'] == 'elevated likelihood' else AMBER if item['result'] == 'unresolved' else GREEN))
    table.setStyle(TableStyle(commands))
    return table


def _criterion(story, item, styles):
    status = {'reported concern': 'Concern', 'no concern reported': 'No concern reported', 'insufficient evidence': 'Insufficient evidence'}.get(item['status'], item['status'])
    code = escape(item['code'])
    title = escape(item['title'])
    story.append(KeepTogether([
        _rich([f'<b>{code} - {title}</b>'], styles['criterion']),
        _rich(['<b>Status:</b> ', escape(status)], styles['body']),
        _rich(['<b>Interpretation:</b> ', escape(item['interpretation'])], styles['body']),
    ]))
    if item['evidence']:
        story.append(_para('Evidence from Interview:', styles['label']))
        for evidence in item['evidence']:
            qid = evidence.get('question_id')
            label = next((q['short_form'] for q in QUESTIONS if q['id'] == qid), 'Supplemental context')
            prefix = f'Q{qid} [{label}]' if qid else label
            story.append(KeepTogether([
                _rich(['<b>', escape(prefix), ':</b> <i>"', escape(evidence['quote']), '"</i>'], styles['quote']),
                _rich(['<b>Interpretation:</b> ', escape(evidence['interpretation'])], styles['quote']),
            ]))
    else:
        story.append(_para('No specific caregiver example was recorded for this observation.', styles['small']))
    if item.get('missing_context') and item['status'] == 'insufficient evidence':
        story.append(_rich(['<b>Information still needed:</b> ', escape(item['missing_context'])], styles['small']))


def pdf(report):
    """Render a validated report with the example's hierarchy and page design."""
    styles = _styles()
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=letter, rightMargin=67, leftMargin=68,
                            topMargin=45, bottomMargin=45, title='ASDWise Screening Report', author='ASDWise')
    story = []
    story.append(_para('ASDWise Screening Report', styles['title']))
    story.append(_para('Child: ' + report['child']['name'], styles['sub']))
    story.append(_para('Generated: ' + _date(report['created']), styles['sub']))
    story.append(Spacer(1, 9))
    story.append(HRFlowable(width='100%', thickness=1, color=LINE, spaceAfter=10))
    s = report['score']
    total = str(s['total']) if s['total'] is not None else 'Incomplete'
    band = s['band'].title() + ' likelihood' if s['band'] != 'INCOMPLETE' else 'Answers need review'
    score_content = [
        _rich([escape(total), '<font size="9" color="#63758c"> / 20</font>' if s['total'] is not None else ''], styles['score']),
        _para(band.upper(), styles['band']),
        _para(s['recommendation'], styles['small']),
    ]
    score_box = Table([[score_content]], colWidths=[477])
    score_box.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), PALE), ('BOX', (0, 0), (-1, -1), .7, LINE),
                                   ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                                   ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    story.extend([score_box, Spacer(1, 7)])
    _section(story, 'M-CHAT-R Item Responses', styles)
    story.append(_item_table(s['items'], styles))
    story.append(PageBreak())
    _section(story, 'Screening Observations (DSM-5-Informed)', styles)
    story.append(_para('These observations describe caregiver reports; they do not establish diagnostic criteria.', styles['small']))
    for index, criterion in enumerate(report['analysis']['criteria']):
        if index == 0:
            story.append(_para('Criterion A: Social Communication and Interaction', styles['group']))
        elif index == 3:
            story.append(_para('Criterion B: Restricted, Repetitive Behaviors', styles['group']))
        _criterion(story, criterion, styles)
    _section(story, 'Overall Assessment', styles)
    story.append(_para(report['analysis']['summary'], styles['body']))
    if report['analysis']['strengths']:
        story.append(_para('Reported strengths', styles['label']))
        for strength in report['analysis']['strengths']:
            story.append(_rich(['&#8226; ', escape(strength)], styles['body']))
    context = report.get('context', {})
    if context.get('other_observations'):
        story.append(_rich(['<b>Other caregiver perspectives, as reported:</b> ', escape(context['other_observations'])], styles['body']))
    for key, label in [('onset', 'Onset'), ('impact', 'Everyday impact'), ('routines', 'Routines'), ('interests', 'Interests')]:
        if context.get(key):
            story.append(_rich([f'<b>{label}:</b> ', escape(context[key])], styles['body']))
    story.append(PageBreak())
    _section(story, 'Recommendations', styles)
    story.append(_para('Based on the ' + s['band'].lower() + ' initial screening result:', styles['body']))
    for title, value in report['recommendations'].items():
        story.append(_para(title.title(), styles['group']))
        story.append(_para(value, styles['body']))
    if report['analysis']['limitations']:
        story.append(_para('Limitations', styles['group']))
        for limitation in report['analysis']['limitations']:
            story.append(_rich(['&#8226; ', escape(limitation)], styles['body']))
    disclaimer = Table([[_rich(['<b>Important Disclaimer:</b> ', escape(report['disclaimer'])], styles['disclaimer'])]], colWidths=[477])
    disclaimer.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff9e9')),
                                    ('LINEBEFORE', (0, 0), (0, 0), 2.5, AMBER),
                                    ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                                    ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    story.extend([Spacer(1, 10), disclaimer])
    doc.build(story)
    return out.getvalue()
