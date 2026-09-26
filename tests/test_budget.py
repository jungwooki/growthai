import asyncio
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import budget, media_storage, server
from backend.web_access import WebAccess


class Store:
    class NoSuchKey(Exception): pass
    exceptions = SimpleNamespace(NoSuchKey=NoSuchKey)
    def __init__(self):
        self.objects = {}
        self.version = 0
        self.conflict = False
    def close(self): pass
    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise self.NoSuchKey()
        raw, etag = self.objects[Key]
        return dict(Body=io.BytesIO(raw), ETag=etag)
    def put_object(self, Bucket, Key, Body, ContentType, ServerSideEncryption, **condition):
        current = self.objects.get(Key)
        conflict = self.conflict or (current and condition.get('IfMatch') != current[1]) or (not current and condition.get('IfNoneMatch') != '*')
        self.conflict = False
        if conflict:
            raise ClientError({'Error': {'Code': 'PreconditionFailed'}, 'ResponseMetadata': {'HTTPStatusCode': 412}}, 'PutObject')
        self.version += 1
        self.objects[Key] = (Body, str(self.version))


@pytest.fixture
def ledger(monkeypatch):
    s3 = Store()
    monkeypatch.setenv('BUDGET_STORAGE', 's3')
    monkeypatch.setenv('MEDIA_S3_BUCKET', 'private-test')
    monkeypatch.setenv('BUDGET_MONTHLY_KRW', '50000')
    monkeypatch.setenv('BUDGET_OVERHEAD_KRW', '10000')
    monkeypatch.setattr(media_storage, 's3_client', lambda: s3)
    return s3


def payload():
    return dict(model='gpt-4.1', instructions='test', input=[], max_output_tokens=8000)


def test_actual_usage_cached_tokens_and_idempotent_settlement(ledger):
    reservation = budget.reserve(payload(), 'extraction')
    assert budget.status()['pending_krw'] > 0
    usage = {'usage': dict(input_tokens=1000, output_tokens=500, input_tokens_details={'cached_tokens': 500})}
    budget.settle(reservation, usage)
    first = budget.status()
    budget.settle(reservation, usage)
    assert budget.status() == first
    assert first['pending_krw'] == 0 and first['ai_estimated_krw'] == 9
    assert first['stages']['extraction'] == 9
    assert first['estimated_total_krw'] == 10009


def test_budget_gate_runs_before_provider_and_owner_approval(ledger, monkeypatch):
    monkeypatch.setenv('BUDGET_MONTHLY_KRW', '10010')
    client = SimpleNamespace(post=AsyncMock())
    with pytest.raises(HTTPException) as error:
        asyncio.run(budget.post_ai(client, payload=payload(), headers={}, stage='interpretation'))
    assert error.value.status_code == 402
    client.post.assert_not_called()
    state = budget.approve(budget.month_now(), 10010, 50000)
    assert state['limit_krw'] == 50000
    assert budget.approve(budget.month_now(), 10010, 50000) == state
    with pytest.raises(HTTPException):
        budget.approve(budget.month_now(), 10010, 60000)
    with pytest.raises(HTTPException):
        budget.approve('2000-01', 50000, 60000)


def test_timeout_retains_uncertain_allowance_and_month_rollover(ledger, monkeypatch):
    client = SimpleNamespace(post=AsyncMock(side_effect=httpx.ReadTimeout('test')))
    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(budget.post_ai(client, payload=payload(), headers={}, stage='interpretation'))
    assert budget.status()['pending_calls'] == 1
    monkeypatch.setattr(budget, 'month_now', lambda: '2030-02')
    assert budget.status()['pending_calls'] == 0
    assert budget.status()['limit_krw'] == 50000


def test_conditional_write_retries_and_unknown_model_fails_closed(ledger):
    ledger.conflict = True
    budget.reserve(payload(), 'extraction')
    assert len(next(iter(ledger.objects.values()))[0]) > 0
    assert budget.status()['pending_calls'] == 1
    p = payload();p['model'] = 'unknown'
    with pytest.raises(HTTPException):
        budget.reserve(p, 'extraction')
    assert budget.status()['pending_calls'] == 1


def test_concurrent_reservations_cannot_oversubscribe(ledger, monkeypatch):
    # Inject another successful request between the first read and conditional write.
    monkeypatch.setenv('BUDGET_MONTHLY_KRW', '10200')
    original = ledger.put_object
    once = [True]
    def interleave(**kwargs):
        if once[0]:
            once[0] = False
            budget.reserve(payload(), 'interpretation')
        return original(**kwargs)
    ledger.put_object = interleave
    with pytest.raises(HTTPException) as error:
        budget.reserve(payload(), 'extraction')
    assert error.value.status_code == 402
    assert budget.status()['pending_calls'] == 1


def test_authentication_required_to_view_or_approve(ledger, monkeypatch):
    monkeypatch.setattr(server, 'ACCESS', WebAccess(True, frozenset({'testserver'}), 'doctor', 'test-password-123456'))
    client = TestClient(server.app, base_url='https://testserver')
    assert client.get('/api/budget').status_code == 401
    assert client.post('/api/budget/approve', json={}).status_code == 401


def test_disabled_budget_does_not_create_fake_zero_spend(monkeypatch):
    monkeypatch.delenv('BUDGET_STORAGE', raising=False)
    assert budget.status() == {'enabled': False}


def test_lambda_execution_role_uses_default_credentials(monkeypatch):
    import boto3
    for key in ('MEDIA_AWS_ROLE_ARN', 'MEDIA_AWS_PROFILE', 'MEDIA_AWS_ACCESS_KEY_ID', 'MEDIA_AWS_SECRET_ACCESS_KEY', 'VERCEL'):
        monkeypatch.delenv(key, raising=False)
    for key, value in dict(MEDIA_STORAGE='s3', MEDIA_S3_BUCKET='test',
                           MEDIA_S3_REGION='ap-southeast-2', MEDIA_SIGNING_SECRET='s'*32,
                           MEDIA_AWS_RUNTIME_ROLE='1', AWS_LAMBDA_FUNCTION_NAME='test').items():
        monkeypatch.setenv(key, value)
    def make(service, **kwargs):
        assert service == 's3'
        assert not any('access_key' in key for key in kwargs)
        return 'role-client'
    monkeypatch.setattr(boto3, 'client', make)
    assert media_storage.configured()
    assert media_storage.s3_client() == 'role-client'
    monkeypatch.setenv('VERCEL', '1')
    assert not media_storage.configured()
