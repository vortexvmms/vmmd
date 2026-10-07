from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import fitz
import pytest
from fastapi import HTTPException

from app.modules.equipment.billing import calculate_billing, billing_amount
from app.modules.equipment.exports import xlsx_summary, pdf_summary, combine_documents
from app.modules.equipment.operations import document_mime
from app.modules.equipment.router import _normalise_extraction


@pytest.mark.parametrize("mode,start,end,break_minutes,basic,ot,total,amount",[
    ("day","07:00","18:00",60,10,0,10,"1000.00"),
    ("day","08:00","20:30",60,10,1.5,11.5,"1180.00"),
    ("night","19:00","07:00",0,10,2,12,"1240.00"),
    ("night","20:00","08:00",60,10,1,11,"1120.00"),
    ("day","08:00","13:30",30,5,0,5,"500.00"),
])
def test_tipper_hours_and_separate_manual_ot_rate(mode,start,end,break_minutes,basic,ot,total,amount):
    d={"billing_mode":mode,"start_time":start,"end_time":end,"break_minutes":break_minutes,"transport_rate":100,"ot_rate":120}
    result=calculate_billing(d)
    assert (result["normal_hours"],result["ot_hours"],result["total_hours"])==(basic,ot,total)
    assert billing_amount(d)==Decimal(amount)


def test_trip_count_and_legacy_amount_preserved():
    assert billing_amount({"billing_mode":"trip","quantity":3,"transport_rate":85})==Decimal("255.00")
    assert billing_amount({"billing_mode":"legacy","quantity":7.5,"transport_rate":85})==Decimal("637.50")
    with pytest.raises(HTTPException): calculate_billing({"billing_mode":"trip","quantity":1.5})


@pytest.mark.parametrize("data",[
    {"start_time":"07:00","end_time":"07:00","break_minutes":0},
    {"start_time":"07:00","end_time":"07:30","break_minutes":60},
    {"start_time":"19:00","end_time":"08:00","break_minutes":0,"ot_rate":None},
    {"start_time":"99:00","end_time":"08:00","break_minutes":0},
])
def test_reject_invalid_hours_and_missing_ot_rate(data):
    with pytest.raises(HTTPException):calculate_billing({"billing_mode":"day",**data})


def test_ocr_uses_printed_work_date_and_warns_for_quality():
    d=_normalise_extraction({"date":"30/09/2026","start_time":"7:00 PM","end_time":"7:30 AM","quality_warnings":["DO number clipped"]})
    assert d["trip_date"]=="2026-09-30"
    assert d["start_time"]=="19:00" and d["end_time"]=="07:30"
    assert d["quality_warnings"]==["DO number clipped"]
    assert _normalise_extraction({})["trip_date"] is None


def trip():
    return {"trip_date":"2026-09-30","do_no":"DO123","truck_no":"XF1412Y","billing_mode":"night","normal_hours":10,"ot_hours":2,"total_hours":12,"transport_rate":100,"ot_rate":120,"billed_amount":1240,"transport_amount":100,"client":{"name":"Client A"},"site_name":"Site A","driver":{"name":"Driver One"},"pickup_location":"=SUM(A1:A2)"}


def test_native_excel_contains_actual_amount_and_no_injected_formula():
    content=xlsx_summary([trip()])
    with ZipFile(BytesIO(content)) as z:
        xml=z.read("xl/worksheets/sheet1.xml")
        root=ET.fromstring(xml)
        assert b"1240" in xml and b"2026-09-30" in xml
        assert not root.findall('.//{*}f')
        assert b"=SUM(A1:A2)" in xml


def test_summary_and_combined_pdf_preserve_all_source_pages_and_header():
    source=fitz.open()
    for text in ("Original page 1 DO123", "Original page 2 supporting detail"):
        p=source.new_page();p.insert_text((30,100),text)
    data=source.tobytes();source.close()
    output=combine_documents([(trip(),data,"application/pdf")]);bundle=fitz.open(stream=output,filetype="pdf")
    assert len(bundle)==1
    for page in bundle:
        text=page.get_text();assert "DO123" in text and "2026-09-30" in text and "Driver One" in text and "XF1412Y" in text
    assert "Original page 2 supporting detail" in bundle[0].get_text()
    summary=fitz.open(stream=pdf_summary([trip()]*70,"2026-09"),filetype="pdf")
    assert len(summary)>1
    text="".join(p.get_text() for p in summary)
    assert "86,800.00" in text and text.count("DO123")==70


def test_document_validation_rejects_fake_and_encrypted_or_long_pdf():
    with pytest.raises(HTTPException):document_mime(b"not an image")
    doc=fitz.open()
    for _ in range(11):doc.new_page()
    with pytest.raises(HTTPException):document_mime(doc.tobytes())
