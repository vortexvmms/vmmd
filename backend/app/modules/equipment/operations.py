"""Driver intake, rate directory, review and exports for tipper supply."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import Depends, Header, HTTPException, Request, Response

from ...db import service_headers, require_service
from ...settings import SUPABASE_URL
from ...storage import _presign
from .schemas import TripCreate, RateRule, DriverConfirm
from .schemas import MasterCreate
from .exports import xlsx_summary, pdf_summary, combine_documents

MAX_UPLOAD = 10 * 1024 * 1024
MAX_PDF_PAGES = 10


def uuid_text(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError):
        raise HTTPException(422, "Invalid record selection")


async def read_limited(request: Request):
    length=request.headers.get("content-length")
    if length and (not length.isdigit() or int(length)>MAX_UPLOAD):
        raise HTTPException(413,"Each file must be below 10 MB")
    chunks=[]; size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>MAX_UPLOAD:
            raise HTTPException(413,"Each file must be below 10 MB")
        chunks.append(chunk)
    if not size: raise HTTPException(422,"Choose a trip-sheet file")
    return b"".join(chunks)


def document_mime(data: bytes):
    import fitz
    try:
        if data.startswith(b"%PDF"):
            doc=fitz.open(stream=data,filetype="pdf")
            if doc.is_encrypted or not 1<=len(doc)<=MAX_PDF_PAGES:
                raise HTTPException(422,"Use an unlocked PDF with 1–10 pages for one trip sheet")
            doc.close(); return "application/pdf"
        doc=fitz.open(stream=data)
        if len(doc)!=1: raise HTTPException(422,"Upload one trip-sheet photo at a time")
        page=doc[0]
        if page.rect.width<400 or page.rect.height<400:
            raise HTTPException(422,"Photo is too small to read. Retake with the whole sheet visible")
        doc.close()
        if data.startswith(b"\xff\xd8"): return "image/jpeg"
        if data.startswith(b"\x89PNG"): return "image/png"
        if data[:4]==b"RIFF" and data[8:12]==b"WEBP": return "image/webp"
    except HTTPException: raise
    except Exception:
        raise HTTPException(422,"File cannot be read. Use a clear JPG, PNG, WebP or PDF")
    raise HTTPException(415,"Use JPG, PNG, WebP or PDF")


def add_operations(router, context):
    from .router import _require_admin, _require_equipment, _period_bounds, _trip_payload, _gemini_extract, _present_trip

    async def private_store(client,content,mime):
        require_service()
        ext={"application/pdf":"pdf","image/jpeg":"jpg","image/png":"png","image/webp":"webp"}[mime]
        key=f"tipper-private/{uuid4()}.{ext}"
        r=await client.post(f"{SUPABASE_URL}/storage/v1/object/tipper-trip-sheets-private/{key}",content=content,
            headers={**service_headers(),"Content-Type":mime},timeout=60)
        if r.status_code not in (200,201): raise HTTPException(502,"Private file upload failed. Retry the file")
        return key

    @router.post("/intake/preview",status_code=201)
    async def intake_preview(request:Request,x_batch_id:str=Header(default=""),user=Depends(context.get_current_user)):
        _require_equipment(user); require_service()
        async with context.shared_client() as client:
            batch_id=uuid_text(x_batch_id)
            batches=await rest(client,"tipper_import_batches",{"id":"eq."+batch_id,"created_by":"eq."+user["user_id"],"limit":"1"},headers=context.supabase_headers(user["token"]))
            if not batches: raise HTTPException(404,"Your upload batch was not found")
            content=await read_limited(request);mime=document_mime(content);key=await private_store(client,content,mime)
            try:
                extracted=await _gemini_extract(content,mime,{"work_types":["Day Work","Night Work","Trip Basis"]})
            except HTTPException:
                extracted={"warnings":["Automatic reading is unavailable. Review the original and enter the details."],"confidence":0}
            payload={"batch_id":batch_id,"original_name":request.headers.get("x-file-name","Trip sheet")[:300],"image_url":"","image_key":key,"status":"extracted","extracted_data":extracted,"confidence":extracted.get("confidence",0),"warnings":extracted.get("warnings") or []}
            return (await rest(client,"tipper_import_items",method="POST",payload=payload,headers={**context.supabase_headers(user["token"]),"Prefer":"return=representation"}))[0]

    async def rest(client,table,params=None,method="GET",payload=None,headers=None):
        r=await client.request(method,f"{context.rest_url}/{table}",params=params,
            json=payload,headers=headers or {**service_headers(),"Prefer":"return=representation"})
        if r.status_code==409: raise HTTPException(409,"Duplicate record. Check the existing trip sheet or directory entry")
        if r.status_code not in (200,201,204): raise HTTPException(503,"Could not save or load tipper data. Retry shortly")
        return r.json() if r.content else []

    async def link_context(client, token, selected_driver=""):
        require_service()
        if not token or len(token)<32 or len(token)>100:
            raise HTTPException(403,"Upload link is invalid or disabled. Contact your coordinator")
        rows=await rest(client,"tipper_driver_links",{"token_hash":"eq."+hashlib.sha256(token.encode()).hexdigest(),"active":"eq.true","select":"id,driver_id","limit":"1"})
        if not rows:
            portals=await rest(client,"tipper_portal_links",{"token_hash":"eq."+hashlib.sha256(token.encode()).hexdigest(),"active":"eq.true","select":"id","limit":"1"})
            if not portals: raise HTTPException(403,"Upload link is invalid or disabled. Contact your coordinator")
            if not selected_driver: return None,None
            driver_id=uuid_text(selected_driver)
            rows=await rest(client,"tipper_driver_links",{"driver_id":"eq."+driver_id,"select":"id,driver_id,active","limit":"1"})
            if rows and not rows[0]["active"]: raise HTTPException(403,"Driver upload access is disabled. Contact your coordinator")
            if not rows:
                drivers=await rest(client,"tipper_drivers",{"id":"eq."+driver_id,"active":"eq.true","limit":"1"})
                if not drivers: raise HTTPException(403,"Choose an active registered driver")
                owner=await rest(client,"tipper_portal_links",{"id":"eq."+portals[0]["id"],"select":"created_by","limit":"1"})
                rows=await rest(client,"tipper_driver_links",method="POST",payload={"driver_id":driver_id,"token_hash":hashlib.sha256(secrets.token_bytes(32)).hexdigest(),"created_by":owner[0]["created_by"]})
        drivers=await rest(client,"tipper_drivers",{"id":"eq."+rows[0]["driver_id"],"active":"eq.true","select":"id,name,truck_no,provider_id","limit":"1"})
        if not drivers: raise HTTPException(403,"Driver is inactive. Contact your coordinator")
        return rows[0],drivers[0]

    @router.post("/portal-link")
    async def common_link(user=Depends(context.get_current_user)):
        _require_admin(user); require_service(); token=secrets.token_urlsafe(32)
        async with context.shared_client() as client:
            await rest(client,"tipper_portal_links",{"active":"eq.true"},"PATCH",{"active":False})
            await rest(client,"tipper_portal_links",method="POST",payload={"token_hash":hashlib.sha256(token.encode()).hexdigest(),"created_by":user["user_id"]})
            await context.audit(client,user,"rotate_link","tipper_portal","common",None,{"active":True})
        return {"token":token}

    @router.delete("/portal-link")
    async def disable_common_link(user=Depends(context.get_current_user)):
        _require_admin(user); require_service()
        async with context.shared_client() as client:
            await rest(client,"tipper_portal_links",{"active":"eq.true"},"PATCH",{"active":False})
            await context.audit(client,user,"disable_link","tipper_portal","common",None,{"active":False})
        return {"ok":True}

    async def own_submission(client,link,submission_id):
        rows=await rest(client,"tipper_submissions",{"id":"eq."+uuid_text(submission_id),"link_id":"eq."+link["id"],"driver_id":"eq."+link["driver_id"],"limit":"1"})
        if not rows: raise HTTPException(404,"Upload not found for this driver link")
        return rows[0]

    @router.get("/rate-rules")
    async def rates(user=Depends(context.get_current_user)):
        _require_equipment(user)
        async with context.shared_client() as client:
            return await rest(client,"tipper_rate_rules",{"select":"*,client:tipper_clients(name)","order":"client_id,site_name,billing_mode,effective_from.desc"},headers=context.supabase_headers(user["token"]))

    @router.patch("/drivers/{driver_id}")
    async def edit_driver(driver_id:str,body:MasterCreate,user=Depends(context.get_current_user)):
        _require_admin(user)
        async with context.shared_client() as client:
            data={"name":body.name,"phone":body.phone,"truck_no":(body.truck_no or "").strip().upper() or None,"provider_id":body.provider_id}
            rows=await rest(client,"tipper_drivers",{"id":"eq."+uuid_text(driver_id)},"PATCH",data,headers={**context.supabase_headers(user["token"]),"Prefer":"return=representation"})
            if not rows:raise HTTPException(404,"Driver not found")
            await context.audit(client,user,"update","tipper_driver",driver_id,None,data)
            return rows[0]

    @router.post("/rate-rules",status_code=201)
    async def add_rate(body:RateRule,user=Depends(context.get_current_user)):
        _require_admin(user)
        if body.billing_mode in ("day","night") and body.ot_rate is None:
            raise HTTPException(422,"Enter the separate OT rate for this rule")
        data=body.model_dump(mode="json"); data["site_name"]=data["site_name"].strip()
        if not data["site_name"]: raise HTTPException(422,"Enter a site name")
        data["created_by"]=user["user_id"]
        async with context.shared_client() as client:
            rows=await rest(client,"tipper_rate_rules",method="POST",payload=data,headers={**context.supabase_headers(user["token"]),"Prefer":"return=representation"})
            await context.audit(client,user,"create","tipper_rate_rule",rows[0]["id"],None,rows[0])
            return rows[0]

    @router.patch("/rate-rules/{rule_id}/active")
    async def toggle_rate(rule_id:str,active:bool,user=Depends(context.get_current_user)):
        _require_admin(user)
        async with context.shared_client() as client:
            rows=await rest(client,"tipper_rate_rules",{"id":"eq."+uuid_text(rule_id)},"PATCH",{"active":active},headers={**context.supabase_headers(user["token"]),"Prefer":"return=representation"})
            await context.audit(client,user,"update","tipper_rate_rule",rule_id,None,{"active":active})
            return rows

    @router.post("/drivers/{driver_id}/link")
    async def generate_link(driver_id:str,user=Depends(context.get_current_user)):
        _require_admin(user); require_service(); driver_id=uuid_text(driver_id)
        token=secrets.token_urlsafe(32)
        async with context.shared_client() as client:
            drivers=await rest(client,"tipper_drivers",{"id":"eq."+driver_id,"limit":"1"})
            if not drivers: raise HTTPException(404,"Driver not found")
            existing=await rest(client,"tipper_driver_links",{"driver_id":"eq."+driver_id,"limit":"1"})
            data={"driver_id":driver_id,"token_hash":hashlib.sha256(token.encode()).hexdigest(),"active":True,"created_by":user["user_id"]}
            if existing: await rest(client,"tipper_driver_links",{"id":"eq."+existing[0]["id"]},"PATCH",data)
            else: await rest(client,"tipper_driver_links",method="POST",payload=data)
            await context.audit(client,user,"rotate_link","tipper_driver",driver_id,None,{"active":True})
        return {"token":token,"driver":drivers[0]["name"]}

    @router.delete("/drivers/{driver_id}/link")
    async def disable_link(driver_id:str,user=Depends(context.get_current_user)):
        _require_admin(user); require_service()
        async with context.shared_client() as client:
            await rest(client,"tipper_driver_links",{"driver_id":"eq."+uuid_text(driver_id)},"PATCH",{"active":False})
            await context.audit(client,user,"disable_link","tipper_driver",driver_id,None,{"active":False})
        return {"ok":True}

    @router.get("/driver/setup")
    async def driver_setup(x_tipper_link:str=Header(default=""),x_tipper_driver:str=Header(default="")):
        async with context.shared_client() as client:
            link,driver=await link_context(client,x_tipper_link,x_tipper_driver)
            if not driver:
                drivers=await rest(client,"tipper_drivers",{"active":"eq.true","select":"id,name","order":"name.asc"})
                return {"choose_driver":True,"drivers":drivers}
            rules=await rest(client,"tipper_rate_rules",{"active":"eq.true","select":"id,client_id,site_name,billing_mode,effective_from,client:tipper_clients(name)","order":"site_name,effective_from.desc"})
            return {"driver":driver,"sites":rules,"max_upload_mb":10}

    @router.post("/driver/preview",status_code=201)
    async def driver_preview(request:Request,x_tipper_link:str=Header(default=""),x_tipper_driver:str=Header(default="")):
        async with context.shared_client() as client:
            link,driver=await link_context(client,x_tipper_link,x_tipper_driver)
            if not driver: raise HTTPException(422,"Choose your driver name first")
            recent=await rest(client,"tipper_submissions",{"link_id":"eq."+link["id"],"created_at":"gte."+(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),"select":"id","limit":"41"})
            if len(recent)>=40: raise HTTPException(429,"Daily upload limit reached. Contact your coordinator")
            content=await read_limited(request); mime=document_mime(content)
            digest=hashlib.sha256(content).hexdigest()
            existing=await rest(client,"tipper_submissions",{"driver_id":"eq."+driver["id"],"link_id":"eq."+link["id"],"file_hash":"eq."+digest,"limit":"1"})
            if existing: return public_preview(existing[0])
            key=await private_store(client,content,mime)
            # Store before OCR so retry reuses the uploaded original instead of reuploading.
            row=(await rest(client,"tipper_submissions",method="POST",payload={"driver_id":driver["id"],"link_id":link["id"],"file_hash":digest,"source_image_key":key,"source_image_url":"","source_mime":mime,"original_name":request.headers.get("x-file-name","Trip sheet")[:300],"extracted_data":{}}))[0]
            try:
                masters={"work_types":["Day Work","Night Work","Trip Basis"],"drivers":[driver["name"]]}
                extracted=await _gemini_extract(content,mime,masters)
            except HTTPException:
                extracted={"warnings":["Automatic reading is unavailable. Check the sheet and enter the details manually."],"quality_warnings":[],"confidence":0}
            row=(await rest(client,"tipper_submissions",{"id":"eq."+row["id"]},"PATCH",{"extracted_data":extracted,"quality_warnings":extracted.get("quality_warnings") or []}))[0]
            return public_preview(row)

    @router.get("/driver/status")
    async def driver_status(x_tipper_link:str=Header(default=""),x_tipper_driver:str=Header(default="")):
        async with context.shared_client() as client:
            link,driver=await link_context(client,x_tipper_link,x_tipper_driver)
            if not driver: raise HTTPException(422,"Choose your driver name first")
            rows=await rest(client,"tipper_submissions",{"driver_id":"eq."+driver["id"],"status":"in.(pending,approved,rejected)","select":"trip_date,status,trip:tipper_trips(trip_date)","order":"trip_date.desc","limit":"300"})
            groups={}
            for row in rows:
                day=row["trip_date"]
                if row["status"]=="approved":
                    trips=row.get("trip") or []
                    if not trips: continue
                    day=trips[0]["trip_date"]
                groups.setdefault(day,{"date":day,"approved":0,"pending":0,"rejected":0})[row["status"]]+=1
            return sorted(groups.values(),key=lambda r:r["date"],reverse=True)[:14]

    def public_preview(row):
        data=row.get("extracted_data") or {}
        # No client prices, phone directory, stored object keys or other drivers.
        return {"id":row["id"],"status":row["status"],"fields":{k:data.get(k) for k in ("trip_date","do_no","truck_no","trip_sheet_no","pickup_location","delivery_location","quantity","start_time","end_time","work_type")},"warnings":data.get("warnings") or [],"quality_warnings":row.get("quality_warnings") or [],"confidence":data.get("confidence",0)}

    @router.post("/driver/submissions/{submission_id}/confirm")
    async def driver_confirm(submission_id:str,body:DriverConfirm,x_tipper_link:str=Header(default=""),x_tipper_driver:str=Header(default="")):
        if not body.checked: raise HTTPException(422,"Check the extracted details before submitting")
        async with context.shared_client() as client:
            link,driver=await link_context(client,x_tipper_link,x_tipper_driver)
            if not driver: raise HTTPException(422,"Choose your driver name first")
            row=await own_submission(client,link,submission_id)
            if row["status"]!="draft": return {"status":row["status"],"id":row["id"]}
            if row.get("quality_warnings"): raise HTTPException(422,"Photo quality needs attention. Retake and upload a clear, complete sheet")
            selected=await rest(client,"tipper_rate_rules",{"id":"eq."+uuid_text(body.site_rule_id),"active":"eq.true","limit":"1"})
            if not selected: raise HTTPException(422,"Select an available client/site/work type")
            site=selected[0]
            effective=await rest(client,"tipper_rate_rules",{"client_id":"eq."+site["client_id"],"site_name":"eq."+site["site_name"],"billing_mode":"eq."+site["billing_mode"],"active":"eq.true","effective_from":"lte."+body.trip_date.isoformat(),"order":"effective_from.desc","limit":"1"})
            if not effective: raise HTTPException(422,"No rate rule exists for this work date. Contact your coordinator")
            rule=effective[0]
            data=body.model_dump(mode="json",exclude={"checked","site_rule_id"})
            data.update(client_id=rule["client_id"],site_name=rule["site_name"],billing_mode=rule["billing_mode"],transport_rate=rule["transport_rate"],ot_rate=rule["ot_rate"],break_minutes=rule["break_minutes"],rate_snapshot=rule,driver_name=driver["name"])
            if rule["billing_mode"] in ("day","night") and (not body.start_time or not body.end_time): raise HTTPException(422,"Enter the start and end times from the sheet")
            from .billing import calculate_billing
            data=calculate_billing(data)
            await rest(client,"tipper_submissions",{"id":"eq."+row["id"],"status":"eq.draft"},"PATCH",{"confirmed_data":data,"trip_date":body.trip_date.isoformat(),"status":"pending","submitted_at":datetime.now(timezone.utc).isoformat()})
            return {"status":"pending","id":row["id"]}

    @router.get("/submissions")
    async def submissions(month:str|None=None,date_from:str|None=None,date_to:str|None=None,user=Depends(context.get_current_user)):
        _require_equipment(user); start,end=_period_bounds(month,date_from,date_to)
        async with context.shared_client() as client:
            return await rest(client,"tipper_submissions",{"status":"eq.pending","and":f"(trip_date.gte.{start},trip_date.lt.{end})","select":"*,driver:tipper_drivers(name,truck_no,provider_id)","order":"trip_date.asc","limit":"2000"},headers=context.supabase_headers(user["token"]))

    @router.post("/submissions/{submission_id}/approve")
    async def approve(submission_id:str,body:TripCreate,user=Depends(context.get_current_user)):
        _require_admin(user); require_service()
        async with context.shared_client() as client:
            data=_trip_payload(body,user)
            row=await rest(client,"rpc/tipper_approve_submission",method="POST",payload={"p_id":uuid_text(submission_id),"p_trip":data,"p_user":user["user_id"]})
            await context.audit(client,user,"approve","tipper_submission",submission_id,None,{"trip_id":row.get("id")})
            return _present_trip(row)

    @router.post("/submissions/{submission_id}/reject")
    async def reject(submission_id:str,user=Depends(context.get_current_user)):
        _require_admin(user); require_service()
        async with context.shared_client() as client:
            rows=await rest(client,"tipper_submissions",{"id":"eq."+uuid_text(submission_id),"status":"eq.pending"},"PATCH",{"status":"rejected","reviewed_by":user["user_id"]})
            if not rows: raise HTTPException(409,"This submission has already been reviewed")
            await context.audit(client,user,"reject","tipper_submission",submission_id,None,None)
        return {"ok":True}

    @router.patch("/trips/{trip_id}")
    async def edit_trip(trip_id:str,body:TripCreate,user=Depends(context.get_current_user)):
        _require_admin(user)
        async with context.shared_client() as client:
            headers={**context.supabase_headers(user["token"]),"Prefer":"return=representation"}
            before=await rest(client,"tipper_trips",{"id":"eq."+uuid_text(trip_id),"limit":"1"},headers=headers)
            if not before: raise HTTPException(404,"Trip not found")
            payload=_trip_payload(body,user); payload.pop("created_by",None)
            # Source documents and driver identity stay attached to the reviewed submission.
            for key in ("source","source_image_key","source_image_url","driver_id"):
                payload[key]=before[0].get(key)
            after=await rest(client,"tipper_trips",{"id":"eq."+trip_id},"PATCH",payload,headers=headers)
            await context.audit(client,user,"update","tipper_trip",trip_id,before[0],after[0])
            return _present_trip(after[0])

    async def export_trips(client,month,user,client_id,site_name,provider_id,date_from,date_to,work_type):
        start,end=_period_bounds(month,date_from,date_to)
        params={"select":"*,client:tipper_clients(name),provider:tipper_providers(name),work_type:tipper_work_types(name),driver:tipper_drivers(name)","and":f"(trip_date.gte.{start},trip_date.lt.{end})","review_status":"eq.approved","order":"trip_date.asc,do_no.asc","limit":"1000"}
        if client_id: params["client_id"]="eq."+uuid_text(client_id)
        if provider_id: params["provider_id"]="eq."+uuid_text(provider_id)
        if site_name: params["site_name"]="eq."+site_name
        rows=await rest(client,"tipper_trips",params,headers=context.supabase_headers(user["token"]))
        if len(rows)>=1000: raise HTTPException(422,"Select a client and site to export fewer than 1,000 records")
        if work_type not in (None,"all","day","night","day-night","trip"):
            raise HTTPException(422,"Choose a valid work type filter")
        if work_type and work_type!="all":
            wanted={"day","night"} if work_type=="day-night" else {work_type}
            def mode(r):
                if r.get("billing_mode")!="legacy":return r.get("billing_mode")
                name=(r.get("work_type") or {}).get("name","").lower()
                return "trip" if "trip" in name else "night" if "night" in name else "day" if "day" in name else "legacy"
            rows=[r for r in rows if mode(r) in wanted]
        return rows

    def document_request(key):
        if ".." in key: raise HTTPException(422,"Invalid document path")
        if key.startswith("tipper-private/"):
            require_service()
            return f"{SUPABASE_URL}/storage/v1/object/tipper-trip-sheets-private/{key}",service_headers()
        if key.startswith("tipper-trip-sheets/"):return _presign(key,"GET"),{}
        raise HTTPException(422,"Invalid document path")

    @router.get("/documents/{kind}/{record_id}")
    async def original_document(kind:str,record_id:str,user=Depends(context.get_current_user)):
        _require_equipment(user)
        table={"trip":"tipper_trips","submission":"tipper_submissions","import":"tipper_import_items"}.get(kind)
        if not table: raise HTTPException(404,"Document not found")
        async with context.shared_client() as client:
            rows=await rest(client,table,{"id":"eq."+uuid_text(record_id),"limit":"1"},headers=context.supabase_headers(user["token"]))
            if not rows:raise HTTPException(404,"Document not found")
            key=rows[0].get("source_image_key") or rows[0].get("image_key")
            if not key:raise HTTPException(404,"No source sheet is attached")
            url,headers=document_request(key)
            r=await client.get(url,headers=headers,timeout=60)
            if r.status_code!=200:raise HTTPException(502,"Original document could not be read")
            if len(r.content)>MAX_UPLOAD:raise HTTPException(413,"Source document is too large")
            mime=document_mime(r.content)
            return Response(r.content,media_type=mime,headers={"Cache-Control":"no-store","Content-Disposition":"inline"})

    @router.get("/export/{kind}")
    async def export(kind:str,month:str|None=None,client_id:str|None=None,site_name:str|None=None,provider_id:str|None=None,date_from:str|None=None,date_to:str|None=None,work_type:str|None=None,user=Depends(context.get_current_user)):
        _require_equipment(user)
        if kind not in ("xlsx","summary-pdf","documents-pdf"): raise HTTPException(404,"Unknown export")
        async with context.shared_client() as client:
            rows=await export_trips(client,month,user,client_id,site_name,provider_id,date_from,date_to,work_type)
            period=f"{date_from}_to_{date_to}" if date_from else month
            if kind=="xlsx": data=xlsx_summary(rows); mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"; ext="xlsx"
            elif kind=="summary-pdf": data=pdf_summary(rows,period); mime="application/pdf"; ext="pdf"
            else:
                if not rows: raise HTTPException(422,"No approved trip sheets for this month/filter")
                missing=[r.get("do_no") for r in rows if not r.get("source_image_key")]
                if missing: raise HTTPException(422,"Some approved trips have no attached sheet: "+", ".join(str(x) for x in missing[:8])+". Attach the sheets before exporting the complete bundle")
                documents=[]; total=0
                for row in rows:
                    key=row["source_image_key"]
                    url,headers=document_request(key)
                    # Signed reads avoid exposing credentials or accepting arbitrary URLs.
                    async with client.stream("GET",url,headers=headers,timeout=60) as r:
                        if r.status_code!=200: raise HTTPException(502,"A trip sheet could not be read. Export was stopped to avoid an incomplete bundle")
                        parts=[]; size=0
                        async for chunk in r.aiter_bytes():
                            size+=len(chunk); total+=len(chunk)
                            if size>MAX_UPLOAD or total>80*1024*1024: raise HTTPException(422,"Bundle is too large. Filter by client/site and export smaller bundles")
                            parts.append(chunk)
                        content=b"".join(parts)
                        mime_source=document_mime(content)
                        documents.append((row,content,mime_source))
                try: data=combine_documents(documents)
                except Exception: raise HTTPException(422,"A source sheet could not be combined. Check the original file")
                mime="application/pdf"; ext="pdf"
        return Response(data,media_type=mime,headers={"Content-Disposition":f'attachment; filename="VCMS_Tipper_{period}_{kind}.{ext}"',"Cache-Control":"no-store"})
