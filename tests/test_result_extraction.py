import copy
import io
import json
import sys
from pathlib import Path

import fitz
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import server, result_extraction as extraction
from test_media_storage import storage, record


def measurement(**kwargs):
    return dict(item='체중', value='55.5', unit='kg', exam_date='2026-09-05',
                location='1쪽 현재 결과', reference='52.7–71.3',
                note='', status='read', **kwargs)


def png():
    with fitz.open() as doc:
        page = doc.new_page(width=120, height=80)
        page.insert_text((10, 25), 'SYNTHETIC ONLY')
        return page.get_pixmap().tobytes('png')


@pytest.mark.parametrize('direct', [False, True])
def test_extract_review_then_synthesize_without_sheet_images(monkeypatch, storage, direct):
    client = TestClient(server.app)
    raw = png()
    patient = dict(sex=1, birth='2013-01-01', exam='2026-09-05', height=168.8,
                   use_ai=True, consent=True)
    calls = []
    async def read(content, summaries):
        calls.append('extract')
        markers = [c['text'] for c in content if c.get('text', '').startswith('PATIENT_FILE')]
        assert len(markers) == 1 and 'F02' in markers[0]
        assert sum(c['type'] == 'input_image' for c in content) == 1
        return dict(documents=[dict(file_id='F02', measurements=[measurement()], warnings=[])],
                    fingerprints=extraction.fingerprints(summaries), usage={'total_tokens': 10})
    async def synthesize(p, metrics, selected, content, summaries):
        calls.append('synthesize')
        assert sum(c['type'] == 'input_image' for c in content) == 1
        assert summaries[0]['visual'] and not summaries[1]['visual']
        sheet = next(c['text'] for c in content if c.get('text', '').startswith('REVIEWED_RESULT'))
        assert '56.0' in sheet and '55.5' not in sheet
        assert p.weight is None  # No silent overwrite of entered measurements.
        return dict(sources=[], clinical_report={'phv': {'label': 'test'}})
    monkeypatch.setattr(extraction, 'extract', read)
    monkeypatch.setattr(server, 'ask_ai', synthesize)
    ticket = None
    if direct:
        batch = client.post('/api/uploads', json={'files': [
            record(raw, 'ulna.png', 'ulna'), record(raw, 'sheet.png', 'extra')]}).json()
        ticket = batch['ticket']
        for upload in batch['uploads']:
            storage[upload['fields']['key']] = (raw, 'image/png')
    def submit():
        if direct:
            return client.post('/api/evaluate-uploaded', json={'patient': patient, 'ticket': ticket})
        return client.post('/api/evaluate', data={'patient': json.dumps(patient),
                           'file_groups': json.dumps(['ulna', 'extra'])},
                           files=[('files', ('ulna.png', raw, 'image/png')),
                                  ('files', ('sheet.png', raw, 'image/png'))])
    first = submit()
    assert first.status_code == 200, first.text
    assert first.json()['stage'] == 'review_records'
    assert calls == ['extract']
    data = first.json()['extraction']
    doc = data['documents'][0]
    doc['measurements'][0].update(value='56.0', include=True)
    patient['reviewed_records'] = dict(confirmed=True, fingerprints=data['fingerprints'], documents=[doc])
    second = submit()
    assert second.status_code == 200, second.text
    assert second.json()['reviewed_records'][0]['measurements'][0]['value'] == '56.0'
    assert calls == ['extract', 'synthesize']
    submit()
    assert calls == ['extract', 'synthesize', 'synthesize']  # No OCR charge on retry.
    patient['reviewed_records']['fingerprints']['F02'] = 'different-file'
    assert submit().status_code == 422
    assert calls == ['extract', 'synthesize', 'synthesize']


def test_unreadable_values_excluded_and_duplicate_sources_rejected():
    summaries = [dict(id='F01', group='extra', sha256='abc')]
    row = measurement(include=False)
    row.update(value=None, status='needs_review')
    review = extraction.Review(confirmed=True, fingerprints={'F01': 'abc'},
                              documents=[dict(file_id='F01', measurements=[row], warnings=['unclear'])])
    assert extraction.checked_values(review, summaries)[0]['measurements'] == []
    review.documents[0].measurements[0].include = True
    with pytest.raises(HTTPException):
        extraction.checked_values(review, summaries)
    review.documents[0].measurements[0].include = False
    review.documents.append(review.documents[0])
    with pytest.raises(HTTPException):
        extraction.checked_values(review, summaries)


def test_consent_and_basic_mode_never_extract(monkeypatch):
    async def forbidden(*args):
        pytest.fail('Must not call extraction or AI')
    monkeypatch.setattr(extraction, 'extract', forbidden)
    monkeypatch.setattr(server, 'ask_ai', forbidden)
    client = TestClient(server.app)
    p = dict(sex=1, birth='2013-01-01', exam='2026-09-05', height=168.8, use_ai=True)
    def submit():
        return client.post('/api/evaluate', data={'patient': json.dumps(p)},
                           files=[('files', ('sheet.txt', b'Weight 55.5 kg', 'text/plain'))])
    assert submit().status_code == 422
    p['use_ai'] = False
    assert submit().status_code == 200


@pytest.mark.parametrize('mode', ['completed', 'incomplete', 'wrong_file', 'refusal', 'http_error'])
def test_provider_validation_and_usage(monkeypatch, mode):
    import asyncio
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only')
    doc = dict(file_id='F02' if mode == 'wrong_file' else 'F01',
               measurements=[measurement()], warnings=[])
    payload = dict(status='incomplete' if mode == 'incomplete' else 'completed',
                   output=[{'content': [] if mode == 'refusal' else [
                       dict(type='output_text', text=json.dumps({'documents': [doc]}))]}],
                   usage=dict(input_tokens=100, output_tokens=30, total_tokens=130,
                              input_tokens_details={'cached_tokens': 50}))
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            assert kwargs['json']['store'] is False
            assert '참고범위' in kwargs['json']['instructions']
            return httpx.Response(429 if mode == 'http_error' else 200, json=payload)
    monkeypatch.setattr(extraction.httpx, 'AsyncClient', Client)
    async def run():
        return await extraction.extract([dict(type='input_text', text='test')],
                                        [dict(id='F01', group='extra', sha256='abc')])
    if mode == 'completed':
        result = asyncio.run(run())
        assert result['usage']['total_tokens'] == 130 and result['cached_tokens'] == 50
    else:
        with pytest.raises(HTTPException) as error:
            asyncio.run(run())
        assert error.value.status_code == 502
