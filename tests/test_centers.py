import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend import centers, budget, media_storage, server
from backend.web_access import WebAccess
from test_budget import ledger, payload
from test_media_storage import storage, record

PASSWORD='test-only-password-2026'

@pytest.fixture
def accounts(monkeypatch):
    hashed=centers.hash_password(PASSWORD)
    data=dict(centers=centers.DEFAULT_CENTERS,users=[
        dict(username='seoul',role='center',center_id='seoul-rnd',password_hash=hashed),
        dict(username='dongtan',role='center',center_id='gyeonggi-dongtan',password_hash=hashed),
        dict(username='hq',role='headquarters',password_hash=hashed)])
    monkeypatch.setenv('APP_CENTER_AUTH_JSON',json.dumps(data))
    monkeypatch.setenv('APP_SESSION_SECRET','test-session-secret-'*3)
    monkeypatch.setattr(server,'ACCESS',WebAccess(False,frozenset({'testserver'}),'legacy','legacy-password-long'))
    return data

def sign_in(client,user):
    response=client.post('/api/auth/login',json=dict(username=user,password=PASSWORD))
    assert response.status_code==200
    return response

def test_roles_and_shared_login_disabled(accounts):
    with TestClient(server.app) as client:
        assert client.get('/headquarters',follow_redirects=False).status_code==303
        assert client.post('/api/auth/login',json=dict(username='legacy',password='legacy-password-long')).status_code==401
        assert sign_in(client,'seoul').json()['redirect']=='/workspace'
        assert client.get('/api/auth/me').json()['center']['id']=='seoul-rnd'
        assert client.get('/headquarters').status_code==403
        assert client.post('/api/budget/approve',json={}).status_code==403
        sign_in(client,'hq')
        assert client.get('/headquarters').status_code==200
        for endpoint in ['/api/evaluate','/api/media/uploads','/api/preview']:
            assert client.post(endpoint,json={}).status_code==403
        assert client.get('/workspace').status_code==403
        assert centers.current.get() is None

def test_forged_rotated_and_disabled_sessions(accounts,monkeypatch):
    token,_=centers.authenticate('seoul',PASSWORD)
    assert centers.resolve(token)['center']['id']=='seoul-rnd'
    assert centers.resolve(token+'x') is None
    accounts['users'][0]['active']=False
    monkeypatch.setenv('APP_CENTER_AUTH_JSON',json.dumps(accounts))
    assert centers.resolve(token) is None
    accounts['users'][0]['active']=True
    accounts['users'][0]['password_hash']=centers.hash_password('rotated-password-2026')
    monkeypatch.setenv('APP_CENTER_AUTH_JSON',json.dumps(accounts))
    assert centers.resolve(token) is None

def test_monthly_completion_cost_and_center_privacy(accounts,ledger):
    async def call(stage,complete):
        response=httpx.Response(200,json={'usage':{'input_tokens':1000,'output_tokens':500}})
        await budget.post_ai(SimpleNamespace(post=AsyncMock(return_value=response)),payload=payload(),headers={},stage=stage)
        if complete:
            await budget.completed(response)
            await budget.completed(response)
    for username,stage,complete in [('seoul','extraction',True),('seoul','interpretation',True),('dongtan','interpretation',False)]:
        _,principal=centers.authenticate(username,PASSWORD)
        token=centers.current.set(principal)
        try:asyncio.run(call(stage,complete))
        finally:centers.current.reset(token)
    with TestClient(server.app) as client:
        sign_in(client,'hq')
        data=client.get('/api/usage/monthly').json()
        rows={c['id']:c for c in data['centers']}
        assert rows['seoul-rnd']['completed_interpretations']==1
        assert rows['seoul-rnd']['completed_extractions']==1
        assert rows['gyeonggi-dongtan']['completed_interpretations']==0
        assert rows['gyeonggi-dongtan']['ai_estimated_krw']>0
        assert {r['region'] for r in data['regions']}=={'서울','경기'}
        assert client.get('/api/usage/monthly?month=2026-13').status_code==422
        assert all(c['interpretation_calls']==0 for c in client.get('/api/usage/monthly?month=2020-01').json()['centers'])
        sign_in(client,'seoul')
        private=client.get('/api/usage/monthly?center_id=gyeonggi-dongtan').json()
        assert [c['id'] for c in private['centers']]==['seoul-rnd']
        state=client.get('/api/budget').json()
        assert state['center_only'] and 'limit_krw' not in state
        assert 'gyeonggi-dongtan' not in json.dumps(state)

def test_center_ticket_namespace_and_session_binding(accounts,storage):
    batch=media_storage.UploadBatch(files=[record(b'abc')])
    upload=media_storage.create_upload(batch,'session',center_id='seoul-rnd')
    assert upload['uploads'][0]['fields']['key'].startswith('exams/seoul-rnd/')
    assert media_storage.read_ticket(upload['ticket'],'session',center_id='seoul-rnd')['center_id']=='seoul-rnd'
    for session,center in [('session','gyeonggi-dongtan'),('other','seoul-rnd'),('session',None)]:
        with pytest.raises(HTTPException):media_storage.read_ticket(upload['ticket'],session,center_id=center)

def test_tracking_required_before_ai(accounts,monkeypatch):
    monkeypatch.delenv('BUDGET_STORAGE',raising=False)
    client=SimpleNamespace(post=AsyncMock())
    with pytest.raises(HTTPException):asyncio.run(budget.post_ai(client,payload=payload(),headers={},stage='interpretation'))
    client.post.assert_not_called()

def test_invalid_registry_fails_closed(accounts,monkeypatch):
    monkeypatch.setenv('APP_CENTER_AUTH_JSON','{}')
    with TestClient(server.app) as client:
        assert client.get('/api/auth/me').status_code==503


def test_request_identity_reaches_ai_ledger(accounts,ledger,monkeypatch):
    async def fake_ai(*args,**kwargs):
        budget.reserve(payload(),'interpretation')
        raise HTTPException(502,'synthetic provider failure')
    monkeypatch.setattr(server,'ask_ai',fake_ai)
    patient=dict(sex=1,birth='2013-01-01',exam='2026-09-25',height=150,use_ai=True,consent=True)
    with TestClient(server.app) as client:
        sign_in(client,'dongtan')
        response=client.post('/api/evaluate',data={'patient':json.dumps(patient)})
        assert response.status_code==200
        sign_in(client,'hq')
        rows={c['id']:c for c in client.get('/api/usage/monthly').json()['centers']}
        assert rows['gyeonggi-dongtan']['interpretation_calls']==1
        assert rows['gyeonggi-dongtan']['pending_calls']==1
        assert rows['seoul-rnd']['interpretation_calls']==0
        response=client.post('/api/budget/approve',json=dict(month=budget.month_now(),expected_limit_krw=50000,new_limit_krw=60000))
        assert response.status_code==200
    data,_=budget.read(ledger,budget.month_now())
    assert data['approvals'][0]['approved_by']=='hq'
