from app.modules.lifting.domain import validity,decorate,extract
from app.modules.lifting.pdf import log_pdf,assemble,LM,LG
import fitz


def test_calendar_months_and_expiry_cap():
    assert validity('2026-08-31',6)=='2027-02-27'
    assert validity('2024-02-29',12)=='2025-02-27'
    x=decorate({'examination_date':'2026-05-28','certificate_expiry':'2026-10-01','renewal_months':12},True)
    assert x['next_renewal']=='2026-10-01'


def test_extract_review_fields():
    r=extract('LE Registration No. LM563989N Vehicle XE1807Y Max. Safe Working Load 10400 kg Certificate Expiry Date 27/05/2027 I certify that on 28/05/2026 the lifting equipment was examined thoroughly')['fields']
    assert r['lm_number']=='LM563989N'
    assert r['vehicle_number']=='XE1807Y'
    assert r['swl_kg']==10400
    assert r['certificate_expiry']=='2027-05-27'
    assert r['examination_date']=='2026-05-28'
    assert extract('There are unlabeled dates 20/01/2026 and 20/01/2027')['fields']=={}


def test_multipage_log_and_snapshot_originals():
    rows=[{'machine_id':f'LC-{n}','lm_number':'LM563989N','equipment':'Palfinger PK53002 SH','swl_kg':10400,'remarks':'Certificate maximum only; see load chart.'} for n in range(70)]
    b=log_pdf('Lifting Machine Log',rows,LM,'QA User','2026-09-30')
    d=fitz.open(stream=b,filetype='pdf');assert len(d)>2
    for p in d:
        assert p.rect.width>p.rect.height
        text=p.get_text();assert 'Machine ID' in text and 'Prepared by: QA User' in text and 'Page ' in text
    source=fitz.open();p=source.new_page();p.insert_text((40,40),'Original LM version 1');original=source.tobytes();source.close()
    pack={'generated_at':'2026-09-30T00:00:00Z','document_order':['lm_log','lg_log','doc1'],'snapshot':{'machine':rows[0],'items':[],'documents':[{'id':'doc1','original_filename':'certificate.pdf'}],'prepared_by':'QA User','warnings_acknowledged':False}}
    result=assemble(pack,{'doc1':(original,'application/pdf')});p=fitz.open(stream=result,filetype='pdf')
    assert len(p)==4 and 'Original LM version 1' in p[-1].get_text()
