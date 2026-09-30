import uuid
import json
import pytest
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.modules.lifting.router import LiftingContext,build_lifting_router
from app.modules.lifting.pdf import log_pdf,LM


def client(role='admin'):
    calls=[]
    async def user():return {'role':role,'token':'test','user_id':'profile','auth_uid':'10000000-0000-0000-0000-000000000001','name':'QA User'}
    def transport(req):
        calls.append(req)
        if '/storage/' in str(req.url):return httpx.Response(200,json={'Key':'original'})
        if req.method=='POST':return httpx.Response(201,json=[{'id':str(uuid.uuid4())}])
        return httpx.Response(200,json=[])
    @asynccontextmanager
    async def shared():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as c:yield c
    app=FastAPI();app.include_router(build_lifting_router(LiftingContext(user,shared,'https://db.test/rest/v1',lambda token:{'Authorization':'Bearer '+token},None)))
    return TestClient(app),calls


def test_payroll_blocked_before_database_access():
    c,calls=client('payroll');assert c.get('/api/v1/lifting').status_code==403;assert calls==[]


def test_view_role_can_read_but_not_upload_or_extract():
    c,calls=client('site_sup');assert c.get('/api/v1/lifting').status_code==200
    assert c.post('/api/v1/lifting/extract',json={'text':'LM563989N'}).status_code==403
    assert c.post('/api/v1/lifting/documents?kind=lm&filename=test.pdf',content=b'%PDF-test',headers={'Content-Type':'application/pdf'}).status_code==403


def test_upload_validates_content_and_keeps_unverified():
    c,calls=client();bad=c.post('/api/v1/lifting/documents?kind=lm&filename=test.pdf',content=b'not a pdf',headers={'Content-Type':'application/pdf'});assert bad.status_code==415;assert not calls
    pdf=log_pdf('Test',[],LM,'QA User');r=c.post('/api/v1/lifting/documents?kind=lm&filename=test.pdf',content=pdf,headers={'Content-Type':'application/pdf'});assert r.status_code==201
    import json
    record=json.loads(calls[-1].content);assert record['object_key'].startswith('originals/')
    assert record['created_by']=='10000000-0000-0000-0000-000000000001';assert 'verified' not in record
    assert record['file_size']==len(pdf) and len(record['checksum'])==64


def test_invalid_record_identifiers_are_rejected():
    c,_=client();assert c.get('/api/v1/lifting/documents/not-an-id/file').status_code==422
    assert c.post('/api/v1/lifting/packs',json={'machine_id':'not-an-id','order':[]}).status_code==422


@pytest.mark.parametrize('header',['application/pdf','application/pdf; charset=binary','application/octet-stream','application/json',''])
def test_pdf_upload_uses_validated_file_bytes_not_client_header(header):
    c,calls=client();pdf=log_pdf('Certificate',[],LM,'QA User')
    r=c.post('/api/v1/lifting/documents?kind=lm&filename=certificate.pdf',content=pdf,headers={'Content-Type':header})
    assert r.status_code==201
    record=json.loads(calls[-1].content)
    assert record['mime_type']=='application/pdf'
    assert calls[0].headers['content-type']=='application/pdf'
    assert calls[0].content==pdf


@pytest.mark.parametrize('filetype,mime',[('png','image/png'),('jpeg','image/jpeg')])
def test_image_upload_detects_and_validates_original(filetype,mime):
    import fitz
    with fitz.open(stream=log_pdf('Certificate',[],LM,'QA User'),filetype='pdf') as doc:
        data=doc[0].get_pixmap().tobytes(filetype)
    c,calls=client()
    r=c.post('/api/v1/lifting/documents?kind=lm&filename=certificate.'+filetype,content=data,headers={'Content-Type':'application/octet-stream'})
    assert r.status_code==201 and json.loads(calls[-1].content)['mime_type']==mime


def test_pdf_signature_alone_does_not_bypass_document_validation():
    c,calls=client()
    r=c.post('/api/v1/lifting/documents?kind=lm&filename=certificate.pdf',content=b'%PDF-not a readable document',headers={'Content-Type':'application/json'})
    assert r.status_code==400 and calls==[]
