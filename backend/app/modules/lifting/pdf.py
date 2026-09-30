"""Landscape register pages and frozen original-document packs."""
from io import BytesIO
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import fitz
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from .domain import decorate

LM = [('machine_id','Machine ID'),('lm_number','LM No.'),('vehicle_number','Vehicle'),('equipment','Equipment'),('swl_kg','Max SWL kg'),('examination_date','Exam date'),('validity_6','6 months'),('validity_12','12 months'),('certificate_expiry','Expiry'),('remarks','Remarks')]
LG = [('lg_number','LG No.'),('gear_type','Gear type'),('size','Size'),('length','Length'),('swl_kg','SWL kg'),('examination_date','Exam date'),('validity_6','6 months'),('validity_12','12 months'),('certificate_expiry','Expiry'),('next_renewal','Next renewal'),('currently_with','Currently with'),('remarks','Remarks')]
LOGO = Path(__file__).resolve().parents[3] / 'assets' / 'vortex-logo.png'

def log_pdf(title, rows, columns, prepared_by, generated=None):
    buf=BytesIO(); styles=getSampleStyleSheet(); style=styles['BodyText']; style.fontSize=7;style.leading=9
    def p(v): return Paragraph(escape(str(v if v is not None and v!='' else '—')),style)
    grid=[[p(label) for _,label in columns]]+[[p(row.get(k)) for k,_ in columns] for row in rows]
    if len(grid)==1: grid.append([p('No records')]+[p('') for _ in columns[1:]])
    widths=[(landscape(A4)[0]-64)/len(columns)]*len(columns)
    table=Table(grid,colWidths=widths,repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5eaf2')),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#cdd4df')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    stamp=(datetime.fromisoformat(generated.replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Singapore')).date().isoformat() if generated and 'T' in generated else generated or datetime.now(ZoneInfo('Asia/Singapore')).date().isoformat())
    def page(canvas,doc):
        w,h=landscape(A4); canvas.saveState()
        if LOGO.exists(): canvas.drawImage(str(LOGO),32,h-46,width=105,height=25,preserveAspectRatio=True,mask='auto')
        canvas.setFont('Helvetica-Bold',13);canvas.drawString(152,h-35,title)
        canvas.setFont('Helvetica',8);canvas.drawString(32,h-61,f'Prepared by: {prepared_by}   |   Date: {stamp}')
        canvas.drawString(32,19,f'Page {doc.page}');canvas.restoreState()
    SimpleDocTemplate(buf,pagesize=landscape(A4),leftMargin=32,rightMargin=32,topMargin=78,bottomMargin=36).build([table],onFirstPage=page,onLaterPages=page)
    return buf.getvalue()

def cover_pdf(pack):
    s=pack['snapshot'];m=s['machine'];b=BytesIO();styles=getSampleStyleSheet()
    story=[Paragraph('Vortex — Client Document Pack',styles['Title']),Spacer(1,20),Paragraph(escape(f"{m['machine_id']} · {m.get('vehicle_number','')} · {m.get('lm_number','')}"),styles['Heading2']),Paragraph(escape(f"Prepared by: {s['prepared_by']} | Date: {pack['generated_at'][:10]}"),styles['Normal']),Spacer(1,15)]
    docs={d['id']:d for d in s['documents']}
    for n,k in enumerate(pack['document_order'],1): story.append(Paragraph(escape(f"{n}. { {'lm_log':'LM Log','lg_log':'LG Log'}.get(k,docs.get(k,{}).get('original_filename','Document')) }"),styles['Normal']))
    if s.get('warnings_acknowledged'): story.extend([Spacer(1,15),Paragraph('Document warnings acknowledged at generation. Review certificate dates and completeness before use.',styles['Normal'])])
    SimpleDocTemplate(b,pagesize=A4).build(story);return b.getvalue()

def assemble(pack, originals):
    s=pack['snapshot'];m=decorate(s['machine']);who=s['prepared_by'];stamp=pack['generated_at']
    gears=[]
    for item in s['items']:
        g=decorate(item['certificate'],True);g['currently_with']=m['machine_id']+' · '+item['marking'];gears.append(g)
    out=fitz.open();c=fitz.open(stream=cover_pdf(pack),filetype='pdf');out.insert_pdf(c);c.close()
    for key in pack['document_order']:
        if key=='lm_log': data=log_pdf('Lifting Machine Log',[m],LM,who,stamp);typ='pdf'
        elif key=='lg_log': data=log_pdf('Lifting Gear Log',gears,LG,who,stamp);typ='pdf'
        else: data,typ=originals[key];typ='pdf' if typ=='application/pdf' else 'png' if typ=='image/png' else 'jpeg'
        doc=fitz.open(stream=data,filetype=typ)
        if not doc.is_pdf:
            converted=fitz.open(stream=doc.convert_to_pdf(),filetype='pdf');doc.close();doc=converted
        out.insert_pdf(doc);doc.close()
    result=out.tobytes(garbage=4,deflate=True);out.close();return result
