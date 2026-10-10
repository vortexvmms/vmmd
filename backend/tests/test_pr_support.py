import asyncio
import uuid
import httpx
import pytest
from fastapi import HTTPException
from app import main

ENTRY=uuid.UUID('40000000-0000-0000-0000-000000000001')
USER={'role':'admin','token':'test','user_id':'u1'}

@pytest.fixture
def transport(monkeypatch):
    calls=[]
    state={'status':200,'mime':'image/png','body':b'\x89PNG\r\n\x1a\nfixture','rows':[{'id':str(ENTRY),'pm_hod':'Teo Zheng Liang'}]}
    def handle(req):
        calls.append(req)
        if req.method=='PATCH':return httpx.Response(state['status'],json=state['rows'])
        return httpx.Response(state['status'],headers={'content-type':state['mime']},content=state['body'])
    client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
    class Context:
        async def __aenter__(self):return client
        async def __aexit__(self,*args):pass
    monkeypatch.setattr(main,'shared_client',Context)
    monkeypatch.setattr(main,'SUPABASE_URL','https://example.supabase.co')
    monkeypatch.setattr(main,'REST','https://example.supabase.co/rest/v1')
    monkeypatch.setattr(main,'R2_PUBLIC_BASE','https://media.example.com')
    return calls,state

def test_public_signature_is_returned_without_forwarding_user_token(transport):
    result=asyncio.run(main.pr_signature_image('https://media.example.com/signatures/site/sig.png',USER))
    assert result.media_type=='image/png'
    assert result.body.startswith(b'\x89PNG')
    assert 'authorization' not in transport[0][0].headers

@pytest.mark.parametrize('url',[
    'http://media.example.com/signatures/a.png',
    'https://attacker.test/signatures/a.png',
    'https://media.example.com.evil.test/signatures/a.png',
    'https://media.example.com/signatures/../../a.png',
    'https://media.example.com/signatures/%252e%252e/a.png',
    'https://media.example.com/camera/a.png',
    'https://user:pass@media.example.com/signatures/a.png',
    'https://media.example.com/signatures/a.svg',
    'https://media.example.com/signatures/a.png?redirect=https://attacker.test',
])
def test_signature_proxy_rejects_untrusted_targets_without_fetching(transport,url):
    with pytest.raises(HTTPException) as error:asyncio.run(main.pr_signature_image(url,USER))
    assert error.value.status_code==400 and not transport[0]

@pytest.mark.parametrize('status,mime,body,expected',[
    (302,'image/png',b'fixture',422),
    (404,'image/png',b'fixture',422),
    (200,'text/html',b'<html>',422),
    (200,'image/png',b'',422),
    (200,'image/png',b'x'*(2*1024*1024+1),413),
])
def test_signature_failures_are_not_printable_success(transport,status,mime,body,expected):
    transport[1].update(status=status,mime=mime,body=body)
    with pytest.raises(HTTPException) as error:asyncio.run(main.pr_signature_image('https://media.example.com/signatures/a.png',USER))
    assert error.value.status_code==expected

def test_coordinator_saves_only_approver_names_with_user_rls(transport):
    import json
    result=asyncio.run(main.pr_directory_approvers(ENTRY,main.PRDirApprovers(pm_hod=' Teo Zheng Liang ',manager_director='Ramasamy Ramesh Kumar'),USER))
    assert result['id']==str(ENTRY)
    request=transport[0][0]
    assert request.headers['authorization']=='Bearer test'
    assert json.loads(request.content)=={'pm_hod':'Teo Zheng Liang','manager_director':'Ramasamy Ramesh Kumar'}

def test_supervisor_cannot_change_shared_defaults(transport):
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.pr_directory_approvers(ENTRY,main.PRDirApprovers(),dict(USER,role='site_sup')))
    assert error.value.status_code==403 and not transport[0]

def test_missing_or_rls_hidden_directory_entry_is_not_false_success(transport):
    transport[1]['rows']=[]
    with pytest.raises(HTTPException) as error:asyncio.run(main.pr_directory_approvers(ENTRY,main.PRDirApprovers(),USER))
    assert error.value.status_code==404
