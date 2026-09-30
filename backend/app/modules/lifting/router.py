from __future__ import annotations
import hashlib
import uuid
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from uuid import UUID
from ...core.roles import ATTENDANCE_ROLES, COORDINATOR_ROLES
from .domain import decorate,extract
from .pdf import LM,LG,log_pdf,assemble

@dataclass(frozen=True)
class LiftingContext:
    get_current_user: Callable
    shared_client: Callable
    rest_url: str
    supabase_headers: Callable
    audit: Callable

class Review(BaseModel):
    data: dict
    target_id: UUID | None = None
class Move(BaseModel):
    from_machine_id: UUID | None = None
    to_machine_id: UUID | None = None
    action: str
    issued_by: str = Field(min_length=1,max_length=120)
    received_by: str = Field(min_length=1,max_length=120)
    remarks: str = Field(default='',max_length=1000)
class Pack(BaseModel):
    machine_id: UUID
    item_ids: list[UUID] = Field(default_factory=list,max_length=100)
    document_ids: list[UUID] = Field(default_factory=list,max_length=100)
    order: list[str] = Field(max_length=102)
    acknowledge_warnings: bool = False
class Text(BaseModel):
    text: str = Field(max_length=100000)

READ=set(ATTENDANCE_ROLES); WRITE=set(COORDINATOR_ROLES+('logistics_sup',))
def require(user,write=False):
    if user['role'] not in (WRITE if write else READ): raise HTTPException(403,'Lifting access is not available for this role')

def build_lifting_router(ctx):
    router=APIRouter(prefix='/api/v1/lifting',tags=['lifting'])
    storage_url=ctx.rest_url.removesuffix('/rest/v1')
    async def request_db(user,table,method='get',params=None,payload=None):
        async with ctx.shared_client() as c:
            r=await c.request(method,f'{ctx.rest_url}/{table}',headers={**ctx.supabase_headers(user['token']),'Prefer':'return=representation'},params=params,json=payload)
            if r.status_code>=400:
                try: message=r.json().get('message','Could not save lifting record')
                except ValueError: message='Could not load lifting records'
                raise HTTPException(409 if r.status_code in (400,409) else 503,message[:300])
            return r.json() if r.content else None
    async def records(user):
        result={}
        for name in ('machines','gear_certificates','gear_items','documents','movements','packs'):
            params={'order':'generated_at.desc' if name=='packs' else 'moved_at.desc' if name=='movements' else 'created_at.desc' if name=='documents' else 'id.asc','limit':'2000'}
            if name=='documents': params['select']='id,kind,original_filename,mime_type,file_size,machine_id,gear_certificate_id,verified,verified_at,created_at,extracted_fields,ocr_used'
            elif name=='packs': params['select']='id,machine_id,generated_by,generated_at'
            params['limit']='1000'; result[name]=[]
            for offset in range(0,20000,1000):
                page=await request_db(user,'lifting_'+name,params={**params,'offset':str(offset)})
                result[name].extend(page)
                if len(page)<1000: break
            else: raise HTTPException(413,'Lifting register exceeds the current loading limit. Contact the administrator to enable paged filtering')
        result['machines']=[decorate(x) for x in result['machines']];result['gear_certificates']=[decorate(x,True) for x in result['gear_certificates']]
        result['can_manage']=user['role'] in WRITE;return result
    async def get_row(user,table,id):
        rows=await request_db(user,table,params={'id':f'eq.{id}','limit':'1'})
        if not rows: raise HTTPException(404,'Record not found')
        return rows[0]
    async def object_bytes(user,doc):
        async with ctx.shared_client() as c:
            r=await c.get(f"{storage_url}/storage/v1/object/authenticated/lifting-documents/{quote(doc['object_key'],safe='/')}",headers=ctx.supabase_headers(user['token']))
            if r.status_code!=200: raise HTTPException(502,'Original document could not be read')
            if hashlib.sha256(r.content).hexdigest()!=doc['checksum']: raise HTTPException(409,'Original document checksum differs from the saved version')
            return r.content
    @router.get('')
    async def directory(user:dict=Depends(ctx.get_current_user)):
        require(user);return await records(user)
    @router.post('/extract')
    async def extraction(body:Text,user:dict=Depends(ctx.get_current_user)):
        require(user,True);return extract(body.text)
    @router.post('/documents',status_code=201)
    async def upload(request:Request,kind:str,filename:str,user:dict=Depends(ctx.get_current_user)):
        require(user,True)
        if kind not in ('lm','lg','load_chart','supporting') or len(filename)>240: raise HTTPException(400,'Invalid document details')
        content=bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content)>20971520: raise HTTPException(413,'Documents must be 20 MB or smaller')
        data=bytes(content);mime=request.headers.get('content-type','')
        signatures={'application/pdf':data.startswith(b'%PDF-'),'image/jpeg':data.startswith(b'\xff\xd8\xff'),'image/png':data.startswith(b'\x89PNG\r\n\x1a\n')}
        if not signatures.get(mime): raise HTTPException(415,'Use a valid PDF, JPG or PNG')
        import fitz
        try:
            d=fitz.open(stream=data,filetype='pdf' if mime=='application/pdf' else 'png' if mime=='image/png' else 'jpeg')
            if d.is_encrypted or not 1<=d.page_count<=150: raise ValueError('Encrypted or too many pages')
            d.close()
        except Exception: raise HTTPException(400,'Document could not be read. Use an unlocked PDF with at most 150 pages')
        id=str(uuid.uuid4());key=f'originals/{id}'
        async with ctx.shared_client() as c:
            r=await c.post(f'{storage_url}/storage/v1/object/lifting-documents/{key}',headers={**ctx.supabase_headers(user['token']),'Content-Type':mime,'x-upsert':'false'},content=data)
            if r.status_code not in (200,201): raise HTTPException(503,'Private lifting storage is not ready or the upload failed')
        rows=await request_db(user,'lifting_documents','post',payload={'id':id,'kind':kind,'original_filename':filename,'object_key':key,'mime_type':mime,'file_size':len(data),'checksum':hashlib.sha256(data).hexdigest(),'created_by':user['auth_uid']})
        return rows[0]
    @router.get('/documents/{document_id}/file')
    async def document_file(document_id:UUID,user:dict=Depends(ctx.get_current_user)):
        require(user);d=await get_row(user,'lifting_documents',document_id)
        return Response(await object_bytes(user,d),media_type=d['mime_type'])
    @router.post('/documents/{document_id}/review')
    async def review(document_id:UUID,body:Review,user:dict=Depends(ctx.get_current_user)):
        require(user,True)
        return await request_db(user,'rpc/lifting_review','post',payload={'p_document_id':str(document_id),'p_data':body.data,'p_target_id':str(body.target_id) if body.target_id else None})
    @router.post('/items/{item_id}/move')
    async def move(item_id:UUID,body:Move,user:dict=Depends(ctx.get_current_user)):
        require(user,True)
        return await request_db(user,'rpc/lifting_move','post',payload={'p_item_id':str(item_id),'p_from':str(body.from_machine_id) if body.from_machine_id else None,'p_to':str(body.to_machine_id) if body.to_machine_id else None,'p_action':body.action,'p_issued':body.issued_by,'p_received':body.received_by,'p_remarks':body.remarks})
    @router.get('/logs/{kind}/pdf')
    async def log(kind:str,user:dict=Depends(ctx.get_current_user)):
        require(user);r=await records(user)
        if kind=='machines': rows=r['machines'];columns=LM;title='Lifting Machine Log'
        elif kind=='gears':
            certs={x['id']:x for x in r['gear_certificates']};machines={x['id']:x['machine_id'] for x in r['machines']}
            rows=[{**certs[x['certificate_id']],'currently_with':machines.get(x['current_machine_id'],'Store')+' · '+x['marking']} for x in r['gear_items']];columns=LG;title='Lifting Gear Log'
        else: raise HTTPException(404,'Unknown log')
        return Response(log_pdf(title,rows,columns,user['name']),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{kind}-log.pdf"'})
    @router.post('/packs',status_code=201)
    async def freeze(body:Pack,user:dict=Depends(ctx.get_current_user)):
        require(user,True)
        return await request_db(user,'rpc/lifting_freeze_pack','post',payload={'p_machine_id':str(body.machine_id),'p_items':list(map(str,body.item_ids)),'p_documents':list(map(str,body.document_ids)),'p_order':body.order,'p_ack':body.acknowledge_warnings})
    @router.get('/packs/{pack_id}/pdf')
    async def pack_pdf(pack_id:UUID,user:dict=Depends(ctx.get_current_user)):
        require(user);p=await get_row(user,'lifting_packs',pack_id);originals={}
        for d in p['snapshot']['documents']: originals[d['id']]=(await object_bytes(user,d),d['mime_type'])
        try: result=assemble(p,originals)
        except Exception: raise HTTPException(422,'A selected document cannot be combined. Review the originals')
        return Response(result,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="lifting-client-pack.pdf"'})
    return router
