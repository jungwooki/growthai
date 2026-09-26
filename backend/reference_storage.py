"""Resolve private reference originals outside the deployment archive."""
import hashlib
import os
from pathlib import Path
import tempfile

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException
from . import media_storage

CACHE = Path(tempfile.gettempdir()) / 'growthai-references'


def object_key(source):
    return f"references/{source['id']}{Path(source['name']).suffix}"


def local_path(source, root):
    return Path(root) / 'data/sources' / source['name']


def availability(sources, root, request):
    available = {s['id']: local_path(s, root).is_file() for s in sources}
    missing = [s for s in sources if not available[s['id']]]
    if not missing or not media_storage.configured():
        return available
    client = None
    try:
        client = media_storage.request_client(request)
        for source in missing:
            try:
                info = client.head_object(Bucket=os.environ['MEDIA_S3_BUCKET'], Key=object_key(source))
                available[source['id']] = info['ContentLength'] == source['size']
            except (BotoCoreError, ClientError):
                available[source['id']] = False
    except (BotoCoreError, ClientError, HTTPException):
        pass  # Report unavailable; never claim readiness from configuration alone.
    finally:
        if client is not None:
            client.close()
    return available


def resolve(sources, root, request):
    paths = {}
    client = None
    try:
        for source in sources:
            path = local_path(source, root)
            if path.is_file():
                paths[source['id']] = path
                continue
            if request is None or not media_storage.configured():
                raise FileNotFoundError(source['id'])
            CACHE.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = CACHE / (source['sha256'] + Path(source['name']).suffix)
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256']:
                paths[source['id']] = path
                continue
            if client is None:
                client = media_storage.request_client(request)
            response = client.get_object(Bucket=os.environ['MEDIA_S3_BUCKET'], Key=object_key(source))
            with response['Body'] as body:
                raw = body.read(source['size'] + 1)
            if len(raw) != source['size'] or hashlib.sha256(raw).hexdigest() != source['sha256']:
                raise ValueError('Reference integrity check failed')
            # Readers only see a complete, verified file, including concurrent requests.
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=CACHE, delete=False) as output:
                    temporary = Path(output.name)
                    output.write(raw)
                temporary.replace(path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            paths[source['id']] = path
    finally:
        if client is not None:
            client.close()
    return paths
