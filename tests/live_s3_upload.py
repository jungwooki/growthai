"""Explicit live smoke test: synthetic files only; removes exactly its own objects.

Run manually, never as part of pytest. Requires boto3[crt] and aws login.
"""
import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import quote

import fitz
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--profile', default='growthai')
    parser.add_argument('--region', default='ap-southeast-2')
    args = parser.parse_args()
    os.environ.update(MEDIA_STORAGE='s3', MEDIA_S3_BUCKET=args.bucket,
                      MEDIA_S3_REGION=args.region, MEDIA_AWS_PROFILE=args.profile,
                      MEDIA_SIGNING_SECRET=secrets.token_urlsafe(48), MEDIA_AWS_ROLE_ARN='',
                      VERCEL='', OPENAI_API_KEY='', APP_USERNAME='', APP_PASSWORD='', APP_ENV='local')
    from fastapi.testclient import TestClient
    from backend import media_storage as media, server
    from backend.web_access import WebAccess
    server.ACCESS = WebAccess(False, frozenset({'testserver'}), '', '')
    client = TestClient(server.app)
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=60)
        page.insert_text((5, 25), 'SYNTHETIC TEST ONLY')
        raw = page.get_pixmap().tobytes('png') + b'\x00' * 400000
    digest = base64.b64encode(hashlib.sha256(raw).digest()).decode()
    groups = ['ulna']*4 + ['radius']*4 + ['femur']*4
    records = [dict(name=f'synthetic-{i}.png', size=len(raw), group=g, sha256=digest) for i,g in enumerate(groups)]
    keys = []
    storage = media.s3_client()
    try:
        response = client.post('/api/uploads', json={'files': records})
        assert response.status_code == 200, response.text
        batch = response.json()
        keys = [u['fields']['key'] for u in batch['uploads']]
        with httpx.Client(timeout=60, follow_redirects=False) as http:
            target = batch['uploads'][0]
            preflight = http.options(target['url'], headers={
                'Origin': 'https://growthai-two.vercel.app', 'Access-Control-Request-Method': 'POST'})
            assert preflight.status_code == 200, f'CORS status: {preflight.status_code}'
            assert preflight.headers.get('access-control-allow-origin') == 'https://growthai-two.vercel.app'
            print('Production-origin CORS: passed')
            denied = http.options(target['url'], headers={
                'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'POST'})
            assert 'access-control-allow-origin' not in denied.headers
            # A signed policy must reject changed bytes and changed file length.
            for invalid in [raw[:-1]+b'X', raw+b'X']:
                rejected = http.post(target['url'], data=target['fields'], files={'file': ('original', invalid)})
                assert rejected.status_code in {400, 403}, f'Tampered upload accepted: {rejected.status_code}'
            print('Storage checksum/size enforcement: passed')
            for target in batch['uploads']:
                uploaded = http.post(target['url'], data=target['fields'], files={'file': ('original', raw)})
                if uploaded.status_code != 204:
                    # No policy fields, credentials, or presigned URLs in output.
                    import re
                    code = re.search(r'<Code>([^<]+)</Code>', uploaded.text)
                    raise RuntimeError(f'S3 upload HTTP {uploaded.status_code}, code={code.group(1) if code else "unknown"}')
            print(f'Uploaded {len(keys)} synthetic originals; total bytes={len(raw)*len(keys)}')
            public_url = f'https://{args.bucket}.s3.{args.region}.amazonaws.com/{quote(keys[0])}'
            assert http.get(public_url, headers={'Range': 'bytes=0-15'}).status_code == 403
            print('Anonymous original access: denied')
        patient = dict(sex=1, birth='2014-01-01', exam='2026-09-26', height=150, use_ai=False)
        body = {'patient': patient, 'ticket': batch['ticket']}
        result = client.post('/api/evaluate-uploaded', json=body)
        assert result.status_code == 200, result.text
        files = result.json()['files']
        assert len(files) == 12 and [f['group'] for f in files] == groups
        assert all(f['sha256'] == digest for f in files)
        assert len(json.dumps(body)) < 24000
        print('Actual S3 -> application -> 12-file evaluation: passed (no AI call)')
    finally:
        if keys:
            assert all(key.startswith(f'exams/{batch["exam_id"]}/') for key in keys)
            cleanup = storage.delete_objects(Bucket=args.bucket, Delete={'Objects': [{'Key': k} for k in keys]})
            assert not cleanup.get('Errors'), 'Synthetic cleanup failed'
            print(f'Removed {len(cleanup.get("Deleted", []))} exact synthetic keys; bucket retained')
        storage.close()


if __name__ == '__main__':
    main()
