from contextlib import asynccontextmanager
from copy import deepcopy
from io import BytesIO
import json
import httpx
import pytest
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.modules.worker_documents.router import WorkerDocumentsContext
from app.modules.worker_photos.router import build_worker_photos_router, portrait

W='10000000-0000-0000-0000-000000000001'

@pytest.fixture
def api():
    image=BytesIO(); Image.new('RGB',(800,400),'red').save(image,format='PNG')
    state={'role':'admin','access':True,'conflict':False,'uploads':[],'writes':[],'audit':[],
           'row':{'id':W,'photo_path':None,'updated_at':'v1'},'image':image.getvalue()}
    def transport(req):
        assert req.headers['Authorization']=='Bearer test'
        if req.url.path.endswith('/rpc/worker_documents_can_access'):
            return httpx.Response(200,json=state['access'])
        if '/storage/v1/' in req.url.path:
            if req.method=='POST':
                assert req.headers['x-upsert']=='false'
                state['uploads'].append(bytes(req.content));return httpx.Response(200,json={})
            return httpx.Response(200,content=portrait(state['image']))
        if req.method=='GET':return httpx.Response(200,json=[deepcopy(state['row'])])
        if state['conflict']:return httpx.Response(200,json=[])
        state['writes'].append(json.loads(req.content));state['row'].update(state['writes'][-1])
        return httpx.Response(200,json=[deepcopy(state['row'])])
    @asynccontextmanager
    async def shared():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as c:yield c
    async def audit(*args):state['audit'].append(args)
    app=FastAPI();app.include_router(build_worker_photos_router(WorkerDocumentsContext(
        lambda:{'role':state['role'],'token':'test'},shared,'https://test/rest/v1',
        lambda t:{'Authorization':'Bearer '+t},audit,'')))
    with TestClient(app) as c:yield c,state

def test_portrait_upload_resize_private_read_and_remove(api):
    c,s=api
    r=c.post('/api/v1/worker-photos/'+W,content=s['image'])
    assert r.status_code==200 and r.json()['photo_path'].startswith(W+'/')
    with Image.open(BytesIO(s['uploads'][0])) as image:
        assert image.size==(480,480) and image.format=='JPEG' and not image.getexif()
    r=c.get('/api/v1/worker-photos/'+W)
    assert r.status_code==200 and r.headers['Cache-Control']=='private, no-store'
    assert c.delete('/api/v1/worker-photos/'+W).status_code==200
    assert s['row']['photo_path'] is None and len(s['audit'])==2
    assert c.get('/api/v1/worker-photos/'+W).status_code==404

@pytest.mark.parametrize('role',['site_sup','main_sup','payroll'])
def test_only_management_can_change_photos(api,role):
    c,s=api;s['role']=role
    assert c.post('/api/v1/worker-photos/'+W,content=s['image']).status_code==403
    assert c.delete('/api/v1/worker-photos/'+W).status_code==403
    assert not s['uploads'] and not s['writes']

def test_scoped_read_blocks_other_sites_and_payroll(api):
    c,s=api;s['role']='site_sup';s['access']=False
    assert c.get('/api/v1/worker-photos/'+W).status_code==404
    s['role']='payroll'
    assert c.get('/api/v1/worker-photos/'+W).status_code==403

def test_bad_large_images_and_concurrent_change(api):
    c,s=api
    assert c.post('/api/v1/worker-photos/'+W,content=b'not an image').status_code==415
    assert c.post('/api/v1/worker-photos/'+W,content=b'x'*(2*1024*1024+1)).status_code==413
    s['conflict']=True
    assert c.post('/api/v1/worker-photos/'+W,content=s['image']).status_code==409
    assert s['row']['photo_path'] is None and not s['writes']
