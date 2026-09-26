import hashlib
import io
import json
from unittest.mock import Mock

import fitz
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from backend import reference_storage as refs, server


@pytest.fixture
def private_source(monkeypatch, tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((30, 30), 'Private reference')
    raw = doc.tobytes()
    doc.close()
    source = dict(id='R01', name='private.pdf', size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    client = Mock()
    client.head_object.return_value = {'ContentLength': len(raw)}
    client.get_object.side_effect = lambda **kwargs: {'Body': io.BytesIO(raw)}
    monkeypatch.setenv('MEDIA_S3_BUCKET', 'private-test')
    monkeypatch.setattr(refs.media_storage, 'configured', lambda: True)
    monkeypatch.setattr(refs.media_storage, 'request_client', lambda request: client)
    monkeypatch.setattr(refs, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(server, 'ROOT', tmp_path)
    monkeypatch.setattr(server, 'MANIFEST', [source])
    monkeypatch.setattr(server, 'SOURCES', {'R01': source})
    return source, client, tmp_path


def test_archive_without_originals_reports_private_storage_and_download(private_source):
    source, storage, root = private_source
    storage.generate_presigned_url.return_value = 'https://private.example/signed'
    client = TestClient(server.app)
    assert client.get('/api/status').json()['references_ready'] is True
    assert client.get('/api/library').json()[0]['available'] is True
    response = client.get('/api/sources/R01', follow_redirects=False)
    assert response.status_code == 302
    assert storage.generate_presigned_url.call_args.kwargs['Params']['Key'] == 'references/R01.pdf'
    storage.get_object.assert_not_called()


def test_s3_missing_or_wrong_size_stays_unavailable(private_source):
    source, storage, root = private_source
    storage.head_object.return_value = {'ContentLength': 1}
    assert TestClient(server.app).get('/api/status').json()['missing_sources'] == ['R01']
    storage.head_object.side_effect = ClientError({'Error': {'Code': '403'}}, 'HeadObject')
    assert TestClient(server.app).get('/api/status').json()['references_ready'] is False


def test_verified_cache_can_render_reference_images(private_source):
    source, storage, root = private_source
    paths = refs.resolve([source], root, Mock())
    assert hashlib.sha256(paths['R01'].read_bytes()).hexdigest() == source['sha256']
    content = server.render_references([{'id': 'R01-P001', 'source': 'R01', 'page': 1}], {'R01-P001'}, {'R01': source}, root, paths)
    assert content[1]['image_url'].startswith('data:image/jpeg;base64,')
    refs.resolve([source], root, Mock())
    storage.get_object.assert_called_once()
    storage.close.assert_called_once()


def test_corrupt_download_is_closed_and_not_cached(private_source):
    source, storage, root = private_source
    body = io.BytesIO(b'corrupt')
    storage.get_object.side_effect = None
    storage.get_object.return_value = {'Body': body}
    with pytest.raises(ValueError, match='integrity'):
        refs.resolve([source], root, Mock())
    assert body.closed
    assert not list(refs.CACHE.iterdir())
    storage.close.assert_called_once()


def test_storage_auth_failure_does_not_report_ready(private_source, monkeypatch):
    from fastapi import HTTPException
    source, storage, root = private_source
    def denied(request):
        raise HTTPException(503, 'Storage authentication failed')
    monkeypatch.setattr(refs.media_storage, 'request_client', denied)
    assert TestClient(server.app).get('/api/status').json()['references_ready'] is False


def test_ai_endpoint_resolves_private_original_before_rendering(private_source, monkeypatch):
    from fastapi import HTTPException
    source, storage, root = private_source
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only')
    page = {'id': 'R01-P001', 'source': 'R01', 'page': 1}
    monkeypatch.setattr(server, 'select_references', lambda *args: ([page], {page['id']}))
    monkeypatch.setattr(server, 'search_pages', lambda *args: [])
    renderer = server.render_references
    rendered = []
    def inspect_render(*args):
        rendered.extend(renderer(*args))
        raise HTTPException(503, 'Test stopped before paid API request')
    monkeypatch.setattr(server, 'render_references', inspect_render)
    patient = dict(sex=1, birth='2014-01-01', exam='2026-01-01', height=150, use_ai=True, consent=True)
    response = TestClient(server.app).post('/api/evaluate', data={'patient': json.dumps(patient)})
    assert response.status_code == 200
    assert response.json()['ai_error'] == 'Test stopped before paid API request'
    assert rendered[1]['image_url'].startswith('data:image/jpeg;base64,')
    storage.get_object.assert_called_once()
