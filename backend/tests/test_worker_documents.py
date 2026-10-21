"""Public API boundary tests; actual RLS is exercised separately in PostgreSQL."""
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import hashlib

import fitz
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.worker_documents.router import WorkerDocumentsContext, build_worker_documents_router

W = '10000000-0000-0000-0000-000000000001'
ID = '30000000-0000-0000-0000-000000000001'


def review(data, pages=1, boxes=None):
    return {'X-Document-Masking': json.dumps({'policy': 'fin-dob-wp-v1', 'sha256': hashlib.sha256(data).hexdigest(),
        'pages': [{'reviewed': True, 'boxes': boxes or []} for _ in range(pages)]})}


@pytest.fixture
def api():
    pix = fitz.Pixmap(fitz.csRGB, (0, 0, 20, 10));pix.clear_with(255)
    state = {'role': 'site_sup', 'access': True, 'writes': [], 'uploads': [], 'reads': [], 'media_status': 200, 'audits': [], 'png': pix.tobytes('png'),
             'row': {'id': ID, 'worker_id': W, 'image_path': W+'/00000000-0000-0000-0000-000000000001.png', 'back_image_path': None, 'category': 'course', 'updated_at': 'version1'}}

    def transport(req):
        path = req.url.path
        if '/rest/v1/' in path or '/storage/v1/' in path:
            assert req.headers['Authorization'] == 'Bearer test'
        if path.endswith('/rpc/worker_documents_can_access'):
            return httpx.Response(200, json=state['access'])
        if path.endswith('/rpc/worker_documents_workers'):
            return httpx.Response(200, json=[{'id': W, 'name': 'Sample Worker', 'worker_code': 'EMP-1', 'status': 'active'}] if state['access'] else [])
        if '/storage/v1/object/' in path:
            if req.method == 'POST':
                state['uploads'].append((str(req.url), bytes(req.content)))
                assert req.headers['x-upsert'] == 'false'
                return httpx.Response(200, json={})
            state['reads'].append(str(req.url))
            return httpx.Response(state['media_status'], content=state['png'])
        if path.startswith('/worker-cards/'):
            assert 'Authorization' not in req.headers
            state['reads'].append(str(req.url))
            return httpx.Response(state['media_status'], content=state['png'])
        assert path.endswith(('/worker_cards', '/worker_certificates'))
        if req.method == 'GET':
            return httpx.Response(200, json=[deepcopy(state['row'])] if state['access'] else [])
        payload = json.loads(req.content)
        if req.method == 'PATCH' and req.url.params['updated_at'] != 'eq.'+state['row']['updated_at']:
            return httpx.Response(200, json=[])
        state['writes'].append(payload)
        state['row'].update(payload, updated_at='version'+str(len(state['writes'])+1))
        return httpx.Response(200, json=[deepcopy(state['row'])])

    @asynccontextmanager
    async def shared():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as c:
            yield c

    async def audit(c, user, action, entity, id, old, new):
        state['audits'].append({'old': old, 'new': new, 'action': action})

    def user():
        return {'role': state['role'], 'token': 'test', 'user_id': '00000000-0000-0000-0000-000000000001'}

    app = FastAPI()
    app.include_router(build_worker_documents_router(WorkerDocumentsContext(user, shared, 'https://test.supabase.co/rest/v1', lambda t: {'Authorization': 'Bearer '+t}, audit, 'https://legacy.example', lambda key: 'https://legacy.example/'+key+'?signed=test')))
    with TestClient(app) as client:
        yield client, state


def test_supervisor_upload_and_edit_preserves_worker_and_previous_file(api):
    c, s = api
    original = deepcopy(s['row'])
    r = c.post(f'/api/v1/worker-documents/cards/upload?worker_id={W}&record_id={ID}&updated_at=version1', content=s['png'], headers=review(s['png']))
    assert r.status_code == 201
    key = r.json()['image_path']
    assert key.startswith(W+'/') and key.endswith('.png') and key != original['image_path']
    assert set(fitz.Pixmap(s['uploads'][0][1]).samples)=={255}
    assert s['row']['worker_id'] == W and s['audits'][0]['old']['image_path'] == original['image_path']
    r = c.patch(f'/api/v1/worker-documents/cards/{ID}', json={'updated_at': r.json()['updated_at'], 'category': 'course', 'label': 'Corrected course', 'expiry_date': None})
    assert r.status_code == 200 and r.json()['label'] == 'Corrected course' and r.json()['expiry_date'] is None


def test_conflict_does_not_overwrite_or_delete_uploaded_original(api):
    c, s = api
    r = c.patch(f'/api/v1/worker-documents/cards/{ID}', json={'updated_at': 'old', 'label': 'Stale edit'})
    assert r.status_code == 409 and not s['writes']
    r = c.post(f'/api/v1/worker-documents/cards/upload?worker_id={W}&record_id={ID}&updated_at=old', content=s['png'], headers=review(s['png']))
    assert r.status_code == 409 and len(s['uploads']) == 1 and not s['writes']


@pytest.mark.parametrize('role', ['site_sup', 'safety_sup', 'wshc', 'logistics_sup', 'admin', 'hr_assistant', 'general_manager', 'operation_manager', 'main_sup', 'wshc_lead'])
def test_authorised_roles_pass_api_role_gate(api, role):
    c, s = api;s['role'] = role
    assert c.get('/api/v1/worker-documents/workers').status_code == 200


def test_outside_allocation_payroll_and_anonymous_do_not_get_files_or_write(api):
    c, s = api;s['access'] = False
    assert c.get(f'/api/v1/worker-documents/cards?worker_id={W}').status_code == 404
    assert c.get(f'/api/v1/worker-documents/cards/{ID}/file').status_code == 404
    assert c.post(f'/api/v1/worker-documents/cards/upload?worker_id={W}', content=s['png']).status_code == 404
    s['role'] = 'payroll';s['access'] = True
    assert c.get('/api/v1/worker-documents/workers').status_code == 403
    assert not s['reads'] and not s['uploads']


def test_private_and_historical_files_are_authorised_no_store(api):
    c, s = api
    r = c.get(f'/api/v1/worker-documents/cards/{ID}/file')
    assert r.status_code == 200 and r.content == s['png'] and r.headers['Cache-Control'] == 'no-store'
    s['row']['image_path'] = 'https://legacy.example/worker-cards/existing/front.jpg'
    assert c.get(f'/api/v1/worker-documents/cards/{ID}/file').status_code == 200
    s['row']['image_path'] = 'http://169.254.169.254/latest/meta-data/'
    assert c.get(f'/api/v1/worker-documents/cards/{ID}/file').status_code == 422
    assert len(s['reads']) == 2


def test_invalid_files_dates_and_identity_fields_are_rejected(api):
    c, s = api
    assert c.post(f'/api/v1/worker-documents/cards/upload?worker_id={W}', content=b'<svg></svg>').status_code == 415
    assert c.post(f'/api/v1/worker-documents/cards/upload?worker_id={W}', content=b'\x89PNG\r\n\x1a\ncorrupt').status_code == 400
    doc = fitz.open();doc.new_page();pdf = doc.tobytes();doc.close()
    assert c.post(f'/api/v1/worker-documents/cards/upload?worker_id={W}', content=pdf).status_code == 415
    assert c.post(f'/api/v1/worker-documents/certificates/upload?worker_id={W}', content=pdf, headers=review(pdf)).status_code == 201
    assert c.patch(f'/api/v1/worker-documents/cards/{ID}', json={'updated_at': 'version1', 'worker_id': W}).status_code == 422
    assert c.patch(f'/api/v1/worker-documents/cards/{ID}', json={'updated_at': 'version1', 'issued_date': '2026-10-20', 'expiry_date': '2026-01-01'}).status_code == 422


def test_file_limits_worker_mismatch_and_missing_back_are_rejected(api):
    c, s = api
    assert c.post(f'/api/v1/worker-documents/cards/upload?worker_id={W}', content=b'x'*(20*1024*1024+1)).status_code == 413
    assert c.post(f'/api/v1/worker-documents/cards/upload?worker_id={W}&side=back', content=s['png']).status_code == 422
    assert c.get(f'/api/v1/worker-documents/cards/{ID}/file?side=back').status_code == 404
    other='10000000-0000-0000-0000-000000000002'
    assert c.post(f'/api/v1/worker-documents/cards/upload?worker_id={other}&record_id={ID}&updated_at=version1', content=s['png']).status_code == 409
    s['row']['image_path']='https://legacy.example/worker-cards/front.jpg?redirect=evil'
    assert c.get(f'/api/v1/worker-documents/cards/{ID}/file').status_code == 422
    assert not s['writes'] and not s['uploads'] and not s['reads']


def test_valid_jpeg_upload_decodes(api):
    c, s = api
    pix=fitz.Pixmap(fitz.csRGB,(0,0,20,10));pix.clear_with(255)
    data=pix.tobytes('jpeg')
    r=c.post(f'/api/v1/worker-documents/cards/upload?worker_id={W}',content=data,headers=review(data))
    assert r.status_code==201 and r.json()['image_path'].endswith('.png')


def test_unavailable_legacy_original_retains_record_and_hides_storage_auth(api):
    c, s = api
    s['row']['image_path']='https://legacy.example/worker-cards/worker/front.jpg'
    original=deepcopy(s['row']);s['media_status']=403
    r=c.get(f'/api/v1/worker-documents/cards/{ID}/file')
    assert r.status_code==502 and 'saved record is retained' in r.json()['detail']
    assert s['row']==original and not s['writes']
    assert s['reads']==['https://legacy.example/worker-cards/worker/front.jpg?signed=test']
    assert 'signed=test' not in r.text


def test_unreviewed_changed_and_invalid_masks_never_reach_storage(api):
    c, s = api
    url=f'/api/v1/worker-documents/cards/upload?worker_id={W}'
    assert c.post(url,content=s['png']).status_code==422
    assert c.post(url,content=s['png'],headers=review(b'different')).status_code==422
    for boxes in [[{'x':0,'y':0,'w':2,'h':1}],
                  [{'x':0,'y':0,'w':1,'h':1,'suffix':'G1234567X'}],
                  [{'x':0,'y':0,'w':1,'h':1,'field':'Date of birth','suffix':'1990'}]]:
        assert c.post(url,content=s['png'],headers=review(s['png'],boxes=boxes)).status_code==422
    header=review(s['png']);p=json.loads(header['X-Document-Masking']);p['pages'][0]['reviewed']=False
    assert c.post(url,content=s['png'],headers={'X-Document-Masking':json.dumps(p)}).status_code==422
    assert not s['uploads'] and not s['writes']


@pytest.mark.parametrize("large_scan", [False, True])
def test_real_ocr_preview_and_saved_copy_keep_only_the_requested_endings(api, large_scan):
    from app.modules.worker_documents.masking import recognise
    c,s=api
    with fitz.open() as doc:
        page=doc.new_page(width=700,height=420)
        for y,text in [(70,'FIN: G1234567X'),(140,'Date of Birth: 12/05/1990'),
                       (210,'Work Permit No: 012345678'),(280,'Expiry: 12/05/2028')]:
            page.insert_text((40,y),text,fontsize=26)
        original=doc[0].get_pixmap(matrix=fitz.Matrix(2,2)).tobytes('png') if large_scan else doc.tobytes()
    r=c.post(f'/api/v1/worker-documents/mask-preview?worker_id={W}',content=original)
    assert r.status_code==200 and r.headers['cache-control']=='no-store'
    p=r.json()
    assert p['recognition']=='suggested'
    assert {(b['field'],b['suffix']) for b in p['boxes']}=={('FIN','567X'),('Date of birth',''),('Work Permit number','5678')}
    assert not s['uploads'] and not s['writes']
    r=c.post(f'/api/v1/worker-documents/certificates/upload?worker_id={W}',content=original,headers=review(original,boxes=p['boxes']))
    assert r.status_code==201
    stored=s['uploads'][-1][1]
    with fitz.open(stream=stored,filetype='pdf') as clean:
        assert not clean[0].get_text()
        pix=clean[0].get_pixmap(matrix=fitz.Matrix(2.5,2.5))
        text=' '.join(str(row[1]) for row in recognise(pix.tobytes('png')))
        assert '567X' in text and '5678' in text
        assert 'G1234567X' not in text and '1990' not in text and '012345678' not in text
        assert '2028' in text  # Issue/expiry dates must not be treated as DOB.


def test_all_pdf_pages_are_required_and_hidden_content_is_removed(api):
    c,s=api
    with fitz.open() as doc:
        for _ in range(2):
            page=doc.new_page(width=200,height=100)
            page.insert_text((15,30),'Hidden FIN G1234567X',render_mode=3)
            page.add_text_annot((80,50),'DOB: 12/05/1990')
        doc.embfile_add('source.txt',b'G1234567X')
        doc.set_metadata({'title':'Original G1234567X'})
        raw=doc.tobytes()
    url=f'/api/v1/worker-documents/certificates/upload?worker_id={W}'
    assert c.post(url,content=raw,headers=review(raw)).status_code==422
    boxes=[{'x':.1,'y':.1,'w':.4,'h':.3,'suffix':''}]
    assert c.post(url,content=raw,headers=review(raw,pages=2,boxes=boxes)).status_code==201
    with fitz.open(stream=s['uploads'][-1][1],filetype='pdf') as clean:
        assert len(clean)==2 and clean.embfile_count()==0 and not clean.metadata.get('title')
        for page in clean:
            assert not page.get_text() and not list(page.annots() or [])
            pix=page.get_pixmap()
            assert pix.pixel(30,20)==(0,0,0)


def test_manual_review_fallback_scope_and_busy_gate(api,monkeypatch):
    from app.modules.worker_documents import masking
    c,s=api
    monkeypatch.setattr(masking,'recognise',lambda _: (_ for _ in ()).throw(RuntimeError('private failure details')))
    url=f'/api/v1/worker-documents/mask-preview?worker_id={W}'
    r=c.post(url,content=s['png'])
    assert r.status_code==200 and r.json()['recognition']=='manual_required' and r.json()['boxes']==[]
    assert 'private failure' not in r.text
    masking._processing.acquire()
    try:
        assert c.post(url,content=s['png']).status_code==429
    finally:
        masking._processing.release()
    s['access']=False
    assert c.post(url,content=s['png']).status_code==404
    assert not s['uploads']
