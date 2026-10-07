"""Monthly summary exports and source-document bundles."""
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape


HEADERS = ["Date", "DO Number", "Truck", "Client", "Site", "Provider", "Work Type",
           "Pickup", "Delivery", "Start", "End", "Basic Hours", "OT Hours", "Total Hours",
           "Trips", "Basic / Trip Rate", "OT Rate", "Amount", "Driver"]


def summary_rows(trips):
    return [[r.get("trip_date"), r.get("do_no"), r.get("truck_no"),
             (r.get("client") or {}).get("name"), r.get("site_name"),
             (r.get("provider") or {}).get("name"),
             {"day":"Day Work","night":"Night Work","trip":"Trip Basis"}.get(r.get("billing_mode"), (r.get("work_type") or {}).get("name")),
             r.get("pickup_location"), r.get("delivery_location"), r.get("start_time"), r.get("end_time"),
             r.get("normal_hours"), r.get("ot_hours"), r.get("total_hours"),
             r.get("quantity") if r.get("billing_mode")=="trip" else None,
             r.get("transport_rate"), r.get("ot_rate"), r.get("billed_amount",r.get("transport_amount")),
             r.get("driver_name") or (r.get("driver") or {}).get("name")] for r in trips]


def xlsx_summary(trips):
    """Write native XLSX with inline strings; untrusted text never becomes a formula."""
    def col(i):
        s=""
        while i:
            i,n=divmod(i-1,26); s=chr(65+n)+s
        return s
    rows=[HEADERS]+summary_rows(trips)
    rows.append(["TOTAL"]+[None]*16+[round(sum(float(r.get("billed_amount",r.get("transport_amount")) or 0) for r in trips),2)])
    body=[]
    for i,row in enumerate(rows,1):
        cells=[]
        for j,value in enumerate(row,1):
            address=f"{col(j)}{i}"
            if isinstance(value,(int,float)):
                cells.append(f'<c r="{address}"><v>{value}</v></c>')
            else:
                text="".join(c for c in str(value or "") if ord(c)>=32 or c in "\n\t")
                cells.append(f'<c r="{address}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>')
        body.append(f'<row r="{i}">'+"".join(cells)+"</row>")
    output=BytesIO()
    with ZipFile(output,"w",ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels",'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Trip Register" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml",'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="19" width="19" customWidth="1"/></cols><sheetData>'+"".join(body)+'</sheetData><autoFilter ref="A1:S'+str(len(rows)-1)+'"/></worksheet>')
    return output.getvalue()


def pdf_summary(trips, month):
    from reportlab.lib.pagesizes import landscape, A3
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    output=BytesIO(); width,_=landscape(A3)
    doc=SimpleDocTemplate(output,pagesize=landscape(A3),leftMargin=20,rightMargin=20,topMargin=20,bottomMargin=20)
    style=ParagraphStyle("cell",fontName="Helvetica",fontSize=7,leading=9,wordWrap="CJK")
    heading=ParagraphStyle("heading",fontName="Helvetica-Bold",fontSize=14,leading=18)
    rows=[[Paragraph(escape(str(v if v is not None else "—")),style) for v in row] for row in [HEADERS]+summary_rows(trips)]
    table=Table(rows,colWidths=[(width-40)/len(HEADERS)]*len(HEADERS),repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#dfe8f5")),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#aab2bf")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3)]))
    total=sum(float(r.get("billed_amount",r.get("transport_amount")) or 0) for r in trips)
    doc.build([Paragraph(f"VCMS — Tipper Truck Summary | {escape(month)}",heading),Spacer(1,12),Paragraph("Approved records only. Work dates determine the reporting month.",style),Spacer(1,8),table,Spacer(1,12),Paragraph(f"TOTAL: SGD {total:,.2f}",heading)])
    return output.getvalue()


def combine_documents(documents):
    import fitz
    # A3 landscape fits two portrait DOs without cropping. PDF/image data stays
    # embedded at source resolution; only the placement is scaled.
    out=fitz.open(); docs=[]; frames=[]
    try:
        for row,content,mime in documents:
            doc=fitz.open(stream=content,filetype="pdf" if mime=="application/pdf" or content.startswith(b"%PDF") else None)
            if not doc.is_pdf:
                converted=fitz.open("pdf",doc.convert_to_pdf());doc.close();doc=converted
            docs.append(doc)
            frames.extend((row,doc,i) for i in range(len(doc)))
        width,height=1190.55,841.89
        for i,(row,doc,page_no) in enumerate(frames):
            if i%2==0:target=out.new_page(width=width,height=height)
            left=12+(i%2)*(width/2)
            right=left+width/2-24
            header=(f"DO: {row.get('do_no','')}   Work Date: {row.get('trip_date','')}\n"
                    f"Driver: {row.get('driver_name') or (row.get('driver') or {}).get('name') or '—'}\n"
                    f"Truck: {row.get('truck_no','')}   Source page: {page_no+1}/{len(doc)}")
            if target.insert_textbox(fitz.Rect(left,12,right,82),header,fontsize=9)<0:
                raise ValueError("Sheet header does not fit")
            target.show_pdf_page(fitz.Rect(left,86,right,height-14),doc,page_no,keep_proportion=True)
        return out.tobytes(garbage=4,deflate=True)
    finally:
        out.close()
        for doc in docs:doc.close()
