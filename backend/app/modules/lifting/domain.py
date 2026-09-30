"""Certificate dates and conservative extraction. Every extracted value needs review."""
import calendar
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def validity(examination, months):
    if not examination:
        return None
    start = date.fromisoformat(str(examination)[:10])
    total = start.year * 12 + start.month - 1 + months
    year, month = divmod(total, 12)
    return (date(year, month + 1, min(start.day, calendar.monthrange(year, month + 1)[1])) - timedelta(days=1)).isoformat()


def decorate(row, gear=False):
    row = dict(row)
    row['validity_6'] = validity(row.get('examination_date'), 6)
    row['validity_12'] = validity(row.get('examination_date'), 12)
    expiry = row.get('certificate_expiry')
    if gear:
        candidates = [d for d in (expiry, validity(row.get('examination_date'), row.get('renewal_months', 6))) if d]
        row['next_renewal'] = min(candidates) if candidates else None
    due = row.get('next_renewal') if gear else expiry
    today = datetime.now(ZoneInfo('Asia/Singapore')).date()
    row['status'] = 'Unverified' if not row.get('current_document_id') else 'Missing date' if not due else 'Expired' if due < today.isoformat() else 'Due soon' if due <= (today + timedelta(days=30)).isoformat() else 'Valid'
    return row


def extract(text):
    fields = {}
    for key, pattern in [('lm_number', r'\bLM\s*\d{5,}[A-Z]?\b'), ('lg_number',r'\bLG\s*[A-Z0-9]+(?:\s*-\s*[A-Z0-9]+)?'),('vehicle_number', r'\b(?:XE|XD|XB|GB)\s*\d{3,4}\s*[A-Z]\b')]:
        hits = re.findall(pattern, text, re.I)
        if hits: fields[key] = re.sub(r'\s+', '', hits[0]).upper()
    labels = {'examination_date':r'(?:date\s+of\s+(?:test|examination)|thorough\s+examination\s+(?:on|date)|last\s+(?:test|examination))', 'certificate_expiry':r'(?:expiry\s+date|date\s+of\s+expiry|valid\s+(?:until|till)|expires\s+on)'}
    for key,label in labels.items():
        m = re.search(label+r'[^0-9]{0,70}(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{1,2}[ \-][A-Za-z]{3,9}[ \-]\d{4}|\d{4}-\d{2}-\d{2})',text,re.I)
        if m:
            for fmt in ('%d/%m/%Y','%d-%m-%Y','%d.%m.%Y','%d %B %Y','%d %b %Y','%d-%b-%Y','%Y-%m-%d'):
                try: fields[key]=datetime.strptime(m[1],fmt).date().isoformat();break
                except ValueError: pass
    exam = re.search(r'[I|]\s+certify\s+that\s+on\s+(\d{1,2}/\d{1,2}/\d{4}).{0,180}examined\s+thoroughly', text, re.I|re.S)
    if exam:
        try: fields['examination_date']=datetime.strptime(exam[1],'%d/%m/%Y').date().isoformat()
        except ValueError: pass
    m=re.search(r'max\.?\s+safe\s+working\s+load[^\d]{0,180}([\d,]+(?:\.\d+)?)\s*(kg|tonnes?|tons?|t)\b',text,re.I)
    if not m and 'lm_number' not in fields:
        m=re.search(r'(?:safe\s+working\s+load|\bSWL\b)[^\d]{0,180}([\d,]+(?:\.\d+)?)\s*(kg|tonnes?|tons?|t)\b',text,re.I)
    if m: fields['swl_kg']=float(m[1].replace(',',''))*(1 if m[2].lower()=='kg' else 1000)
    for key,pattern in [('owner',r'OWNER\s+NAME\s*:?\s*(.*?)\s+OWNER\s+UEN'),('serial_number',r'DISTINCTIVE\s+NO\.?\d?\s*:?\s*([A-Z0-9-]+)'),('equipment',r'BRAND\s+AND\s+MODEL\s*:?\s*(.*?)\s+FLY\s+JIB')]:
        match=re.search(pattern,text,re.I|re.S)
        if match and (key!='serial_number' or any(c.isdigit() for c in match[1])): fields[key]=re.sub(r'\s+',' ',match[1]).strip()
    for gear,pat in [('Bow screw pin shackle',r'(?:bow|screw).*shackle'),('Webbing sling',r'webbing|polyester'),('Chain sling',r'chain\s+sling'),('Wire rope sling',r'wire\s+rope')]:
        if re.search(pat,text,re.I): fields['gear_type']=gear;break
    m=re.search(r'(\d+(?:\.\d+)?)\s*(?:metres?|meters?|m)\s*(?:long|length)|(?:length)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*m\b',text,re.I)
    if m and 'lm_number' not in fields: fields['length']=(m[1] or m[2])+' m'
    qty=re.search(r'(?:QTY|QUANTITY)\s*[:\-]?\s*(\d{1,3})\b',text,re.I)
    if qty: fields['quantity']=int(qty[1])
    if 'lm_number' not in fields:
        length=re.search(r'(\d+(?:\.\d+)?)\s*(?:MTR|METRES?|METERS?)\b',text,re.I)
        if length: fields['length']=length[1]+' m'
    inch=re.search(r'(\d+(?:[ ./]\d+)?)\s*[\"″]\s*(?:BOW|SCREW|SHACKLE|X|×)',text,re.I)
    if inch: fields['size']=inch[1]+' inch'
    return {'fields':fields,'warnings':['Review every value against the original. Confirm the physical marking of each gear item. Dates or ratings without a clear label are left blank.']}
