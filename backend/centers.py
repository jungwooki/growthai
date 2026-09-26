"""Server-owned center identities and signed sessions; no patient data."""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from contextvars import ContextVar
from fastapi import HTTPException

current = ContextVar('center_identity', default=None)
DEFAULT_CENTERS = [
    {'id': 'seoul-rnd', 'name': '해온한의원 신도림 서울R&D센터', 'region': '서울'},
    {'id': 'gyeonggi-dongtan', 'name': '해온한의원 동탄 경기화성동탄센터', 'region': '경기'},
]

def enabled():
    return bool(os.getenv('APP_CENTER_AUTH_JSON'))

def registry():
    try:
        data = json.loads(os.environ['APP_CENTER_AUTH_JSON'])
        if len(os.environ['APP_SESSION_SECRET']) < 32:
            raise ValueError()
        centers = data['centers']
        users = data['users']
        ids = [c['id'] for c in centers]
        names = [u['username'] for u in users]
        if len(set(ids)) != len(ids) or len(set(names)) != len(names):
            raise ValueError()
        for c in centers:
            if not re.fullmatch(r'[a-z0-9-]{1,64}', c['id']) or not c['name'] or not c['region']:
                raise ValueError()
        for u in users:
            if u['role'] not in ('center', 'headquarters') or not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', u['username']):
                raise ValueError()
            if u['role'] == 'center' and u.get('center_id') not in ids:
                raise ValueError()
            if not re.fullmatch(r'pbkdf2_sha256\$600000\$[0-9a-f]{32}\$[0-9a-f]{64}', u['password_hash']):
                raise ValueError()
        return data
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, '센터 계정 설정을 확인해주세요.')

def hash_password(password, salt=None):
    if len(password) < 16:
        raise ValueError('비밀번호는 16자 이상이어야 합니다.')
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'

def identity(user, data):
    center = next((c for c in data['centers'] if c['id'] == user.get('center_id')), None)
    return dict(username=user['username'], role=user['role'], center=center)

def authenticate(username, password):
    data = registry()
    user = next((u for u in data['users'] if u['username'] == username and u.get('active', True)), None)
    stored = user['password_hash'] if user else 'pbkdf2_sha256$600000$'+'0'*32+'$'+'0'*64
    salt = stored.split('$')[2]
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    if not hmac.compare_digest(digest, stored.split('$')[3]) or user is None:
        raise HTTPException(401, '아이디 또는 비밀번호를 확인해주세요.')
    payload = base64.urlsafe_b64encode(json.dumps(dict(user=username, exp=int(time.time())+28800,
        nonce=secrets.token_hex(16), revision=hashlib.sha256(stored.encode()).hexdigest())).encode()).decode()
    signature = hmac.new(os.environ['APP_SESSION_SECRET'].encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload+'.'+signature, identity(user, data)

def resolve(token):
    data = registry()
    try:
        if not token or len(token)>2048:
            return None
        payload, signature = token.split('.')
        expected = hmac.new(os.environ['APP_SESSION_SECRET'].encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        claim = json.loads(base64.urlsafe_b64decode(payload))
        if not 0 < claim['exp']-time.time() <= 28800:
            return None
        user = next((u for u in data['users'] if u['username']==claim['user'] and u.get('active', True)), None)
        if user is None or claim['revision'] != hashlib.sha256(user['password_hash'].encode()).hexdigest():
            return None
        return identity(user, data)
    except (ValueError, KeyError, TypeError):
        return None

def center_id():
    principal = current.get()
    return principal['center']['id'] if principal and principal.get('center') else None

def require_hq():
    if not enabled() or not current.get() or current.get()['role'] != 'headquarters':
        raise HTTPException(403, 'MPS 본부 계정으로 이용해주세요.')
