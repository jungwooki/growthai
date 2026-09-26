import base64
import hashlib
import io
import json
import sys
from pathlib import Path

import fitz
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import media_storage as media, server
from backend.web_access import WebAccess


def record(raw, name='scan.png', group='ulna'):
    return dict(name=name, size=len(raw), group=group,
                sha256=base64.b64encode(hashlib.sha256(raw).digest()).decode())


@pytest.fixture
def storage(monkeypatch):
    for key, value in dict(MEDIA_STORAGE='s3', MEDIA_S3_BUCKET='test-growth-private',
                           MEDIA_S3_REGION='ap-northeast-2', MEDIA_AWS_ACCESS_KEY_ID='test',
                           MEDIA_AWS_SECRET_ACCESS_KEY='test', MEDIA_SIGNING_SECRET='x'*32).items():
        monkeypatch.setenv(key, value)
    # Real SDK signing, no AWS calls. Reads are an in-memory private bucket.
    signer = media.s3_client()
    objects = {}

    class Store:
        generate_presigned_post = signer.generate_presigned_post

        def close(self):
            pass

        def get_object(self, Bucket, Key):
            raw, kind = objects[Key]
            return {'Body': io.BytesIO(raw), 'ContentLength': len(raw), 'ContentType': kind}

    monkeypatch.setattr(media, 's3_client', lambda: Store())
    return objects


def test_policy_pins_size_checksum_type_and_opaque_key(storage):
    batch = media.UploadBatch(files=[record(b'abc', 'patient-name.png')])
    result = media.create_upload(batch, 'session-one')
    fields = result['uploads'][0]['fields']
    policy = json.loads(base64.b64decode(fields['policy']))
    assert ['content-length-range', 3, 3] in policy['conditions']
    assert {'x-amz-checksum-sha256': batch.files[0].sha256} in policy['conditions']
    assert {'x-amz-server-side-encryption': 'AES256'} in policy['conditions']
    assert {'Content-Type': 'image/png'} in policy['conditions']
    assert 'patient-name' not in fields['key']
    assert 'acl' not in fields
    assert len(media.read_ticket(result['ticket'], 'session-one')['files']) == 1


def test_ticket_rejects_tampering_other_session_expiry(storage, monkeypatch):
    result = media.create_upload(media.UploadBatch(files=[record(b'x')]), 'one')
    ticket = result['ticket']
    for value, session in [(ticket+'a', 'one'), (ticket, 'two'), ('invalid', 'one')]:
        with pytest.raises(HTTPException) as error:
            media.read_ticket(value, session)
        assert error.value.status_code == 403
    now = media.time.time()
    monkeypatch.setattr(media.time, 'time', lambda: now+media.TICKET_TTL+1)
    with pytest.raises(HTTPException):
        media.read_ticket(ticket, 'one')


def test_manifest_limits():
    good = record(b'x')
    for files in [[good]*13, [good]*6, [{**good, 'size': media.FILE_LIMIT+1}],
                  [{**good, 'name': '../scan.png'}], [{**good, 'name': 'scan.mp4'}],
                  [{**good, 'sha256': 'invalid'}], [{**good, 'size': 0}]]:
        with pytest.raises(ValidationError):
            media.UploadBatch(files=files)


def test_download_rejects_modified_content_and_disguised_file(storage):
    original = b'\x89PNG\r\n\x1a\nabc'
    item = {**record(original), 'key': 'exams/test/file', 'content_type': 'image/png'}
    storage[item['key']] = (original[:-1]+b'd', 'image/png')
    with pytest.raises(HTTPException) as error:
        media.fetch_file(item)
    assert error.value.status_code == 422
    text = b'not a real image'
    item.update(record(text))
    storage[item['key']] = (text, 'image/png')
    with pytest.raises(HTTPException):
        media.fetch_file(item)
    storage[item['key']] = (text, 'text/plain')
    with pytest.raises(HTTPException):
        media.fetch_file(item)


def test_twelve_originals_over_four_mb_reach_evaluation(storage, monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    # Isolate existing access configuration; simulate a logged-in hosted session.
    access = WebAccess(True, frozenset({'testserver'}), 'doctor', 'test-password-123456')
    monkeypatch.setattr(server, 'ACCESS', access)
    client = TestClient(server.app, base_url='https://testserver')
    client.cookies.set('growthai_session', access.issue_session())
    with fitz.open() as doc:
        page = doc.new_page(width=60, height=40)
        raw = page.get_pixmap().tobytes('png') + b'\x00'*400000
    groups = ['ulna']*4+['radius']*4+['femur']*4
    records = [record(raw, f'image-{i}.png', group) for i, group in enumerate(groups)]
    assert sum(r['size'] for r in records) > 4_000_000
    response = client.post('/api/uploads', json={'files': records})
    assert response.status_code == 200, response.text
    batch = response.json()
    for upload in batch['uploads']:
        storage[upload['fields']['key']] = (raw, 'image/png')
    request = {'patient': dict(sex=1, birth='2014-01-01', exam='2026-09-26', height=150), 'ticket': batch['ticket']}
    assert len(json.dumps(request)) < 24000
    response = client.post('/api/evaluate-uploaded', json=request)
    assert response.status_code == 200, response.text
    result = response.json()
    assert [f['id'] for f in result['files']] == [f'F{i:02d}' for i in range(1,13)]
    assert [f['group'] for f in result['files']] == groups
    assert all(f['visual'] and f['sha256'] == records[0]['sha256'] for f in result['files'])
    assert result['exam_id'] == batch['exam_id']
    assert all(value[0] == raw for value in storage.values())
    assert client.get('/api/status').json()['upload_limit_bytes'] == media.TOTAL_LIMIT

    async def fake_ai(patient, metrics, selected, attachments, summary):
        assert sum(c['type'] == 'input_image' for c in attachments) == 12
        markers = [c['text'] for c in attachments if c['type'] == 'input_text' and c['text'].startswith('PATIENT_FILE')]
        assert len(markers) == 12
        assert all(f'PATIENT_FILE F{i:02d} |' in marker for i, marker in enumerate(markers, 1))
        assert [f['group'] for f in summary] == groups
        return {'sources': [], 'clinical_report': {'phv': {'label': 'synthetic test only'}}}

    monkeypatch.setattr(server, 'ask_ai', fake_ai)
    request['patient'].update(use_ai=True, consent=True)
    response = client.post('/api/evaluate-uploaded', json=request)
    assert response.status_code == 200
    assert response.json()['ai']['clinical_report']['phv']['label'] == 'synthetic test only'


def test_private_routes_require_login(storage, monkeypatch):
    monkeypatch.setattr(server, 'ACCESS', WebAccess(True, frozenset({'testserver'}), 'doctor', 'test-password-123456'))
    client = TestClient(server.app, base_url='https://testserver')
    for route in ['/api/uploads', '/api/evaluate-uploaded']:
        assert client.post(route, json={}).status_code == 401


def test_storage_off_keeps_existing_limit(monkeypatch):
    monkeypatch.delenv('MEDIA_STORAGE', raising=False)
    monkeypatch.setenv('VERCEL', '1')
    status = TestClient(server.app).get('/api/status').json()
    assert status['upload_mode'] == 'server'
    assert status['upload_limit_bytes'] == 4_000_000
    with pytest.raises(HTTPException) as error:
        media.read_ticket('invalid', 'local')
    assert error.value.status_code == 503


@pytest.fixture
def oidc_env(monkeypatch):
    monkeypatch.setenv('MEDIA_STORAGE', 's3')
    monkeypatch.setenv('MEDIA_S3_BUCKET', 'private-test-bucket')
    monkeypatch.setenv('MEDIA_S3_REGION', 'ap-southeast-2')
    monkeypatch.setenv('MEDIA_SIGNING_SECRET', 's'*32)
    monkeypatch.setenv('MEDIA_AWS_ROLE_ARN', 'arn:aws:iam::123456789012:role/growthai-test')
    monkeypatch.setenv('VERCEL', '1')


def test_oidc_uses_request_token_and_session_credentials(oidc_env, monkeypatch):
    import boto3
    from botocore import UNSIGNED
    from types import SimpleNamespace
    seen = []
    class STS:
        def assume_role_with_web_identity(self, **kwargs):
            seen.append(kwargs)
            return {'Credentials': {'AccessKeyId': 'test-access', 'SecretAccessKey': 'test-secret', 'SessionToken': 'test-session'}}
        def close(self):
            pass
    def factory(service, **kwargs):
        assert kwargs['region_name'] == 'ap-southeast-2'
        if service == 'sts':
            assert kwargs['config'].signature_version == UNSIGNED
            return STS()
        assert service == 's3'
        assert kwargs['endpoint_url'] == 'https://s3.ap-southeast-2.amazonaws.com'
        assert kwargs['aws_session_token'] == 'test-session'
        return 's3-client'
    monkeypatch.setattr(boto3, 'client', factory)
    monkeypatch.setenv('VERCEL_OIDC_TOKEN', 'stale-environment-token')
    for token in ('request-one', 'request-two'):
        assert media.request_client(SimpleNamespace(headers={'x-vercel-oidc-token': token})) == 's3-client'
    assert [s['WebIdentityToken'] for s in seen] == ['request-one', 'request-two']
    assert all(s['DurationSeconds'] == 3600 for s in seen)


def test_oidc_missing_token_does_not_fallback_to_keys_or_environment(oidc_env, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv('VERCEL_OIDC_TOKEN', 'stale')
    monkeypatch.setenv('MEDIA_AWS_ACCESS_KEY_ID', 'unused')
    monkeypatch.setenv('MEDIA_AWS_SECRET_ACCESS_KEY', 'unused')
    with pytest.raises(HTTPException) as error:
        media.request_client(SimpleNamespace(headers={}))
    assert error.value.status_code == 503


def test_oidc_auth_error_does_not_expose_token(oidc_env, monkeypatch):
    import boto3
    from botocore.exceptions import ClientError
    from types import SimpleNamespace
    class STS:
        def assume_role_with_web_identity(self, **kwargs):
            raise ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'sensitive-token'}}, 'AssumeRoleWithWebIdentity')
        def close(self):
            pass
    monkeypatch.setattr(boto3, 'client', lambda *a, **kw: STS())
    with pytest.raises(HTTPException) as error:
        media.request_client(SimpleNamespace(headers={'x-vercel-oidc-token': 'sensitive-token'}))
    assert error.value.status_code == 503
    assert 'sensitive-token' not in error.value.detail


def test_local_profile_cannot_enable_hosted_uploads(oidc_env, monkeypatch):
    monkeypatch.delenv('MEDIA_AWS_ROLE_ARN')
    monkeypatch.delenv('MEDIA_AWS_ACCESS_KEY_ID', raising=False)
    monkeypatch.delenv('MEDIA_AWS_SECRET_ACCESS_KEY', raising=False)
    monkeypatch.setenv('MEDIA_AWS_PROFILE', 'growthai')
    assert not media.configured()
    monkeypatch.delenv('VERCEL')
    assert media.configured()
