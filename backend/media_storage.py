"""Private S3 originals; bounded, session-bound direct uploads (images/documents)."""
import base64
import hashlib
import hmac
import io
import json
import os
import time
import uuid
from pathlib import PurePosixPath
from typing import Literal

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FILE_LIMIT = 20 * 1024 * 1024
TOTAL_LIMIT = 240 * 1024 * 1024
MAX_FILES = 12
UPLOAD_TTL = 15 * 60
TICKET_TTL = 60 * 60
TYPES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
         '.webp': 'image/webp', '.pdf': 'application/pdf', '.txt': 'text/plain'}


class MediaFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    size: int = Field(strict=True, gt=0, le=FILE_LIMIT)
    group: Literal['ulna', 'radius', 'femur', 'extra']
    sha256: str

    @field_validator('sha256')
    @classmethod
    def checksum(cls, value):
        try:
            if len(base64.b64decode(value, validate=True)) != 32:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('SHA-256 체크섬 형식이 올바르지 않습니다.')
        return value

    @model_validator(mode='after')
    def format(self):
        if '/' in self.name or '\\' in self.name or any(ord(c) < 32 for c in self.name):
            raise ValueError('파일명에 경로 또는 제어문자를 사용할 수 없습니다.')
        ext = PurePosixPath(self.name).suffix.lower()
        if ext not in TYPES or (self.group != 'extra' and not TYPES[ext].startswith('image/')):
            raise ValueError('초음파는 JPG/PNG/WEBP, 추가자료는 PDF/TXT도 지원합니다. 동영상은 아직 지원하지 않습니다.')
        return self


class UploadBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    files: list[MediaFile] = Field(min_length=1, max_length=MAX_FILES)

    @model_validator(mode='after')
    def limits(self):
        if sum(f.size for f in self.files) > TOTAL_LIMIT:
            raise ValueError('전체 업로드는 240MB 이하로 올려주세요.')
        for group in ('ulna', 'radius', 'femur', 'extra'):
            if sum(f.group == group for f in self.files) > (10 if group == 'extra' else 5):
                raise ValueError('부위별 최대 5장, 추가자료 최대 10개입니다.')
        return self


def configured():
    credentials = (bool(os.getenv('MEDIA_AWS_ROLE_ARN')) or
                   (os.getenv('MEDIA_AWS_RUNTIME_ROLE') == '1' and
                    bool(os.getenv('AWS_LAMBDA_FUNCTION_NAME')) and os.getenv('VERCEL') != '1') or
                   (bool(os.getenv('MEDIA_AWS_PROFILE')) and os.getenv('VERCEL') != '1') or
                   all(os.getenv(k) for k in ('MEDIA_AWS_ACCESS_KEY_ID', 'MEDIA_AWS_SECRET_ACCESS_KEY')))
    return (os.getenv('MEDIA_STORAGE') == 's3' and
            all(os.getenv(k) for k in ('MEDIA_S3_BUCKET', 'MEDIA_S3_REGION')) and credentials and
            len(os.getenv('MEDIA_SIGNING_SECRET', '')) >= 32)


def require_config():
    if not configured():
        raise HTTPException(503, '비공개 업로드 저장소 설정을 완료해주세요.')


def s3_client(oidc_token=None):
    require_config()
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    region = os.environ['MEDIA_S3_REGION']
    endpoint = f'https://s3.{region}.amazonaws.com'
    config = Config(signature_version='s3v4', connect_timeout=10,
                    read_timeout=45, retries={'total_max_attempts': 3, 'mode': 'standard'})
    if os.getenv('MEDIA_AWS_ROLE_ARN'):
        # On Vercel the fresh token comes from this request, never a cached process token.
        token = oidc_token if os.getenv('VERCEL') == '1' else os.getenv('VERCEL_OIDC_TOKEN')
        if not token:
            raise HTTPException(503, 'Vercel의 AWS 연결 인증을 확인해주세요.')
        sts = boto3.client('sts', region_name=region, config=Config(
            signature_version=UNSIGNED, connect_timeout=10, read_timeout=20,
            retries={'total_max_attempts': 2, 'mode': 'standard'}))
        try:
            credentials = sts.assume_role_with_web_identity(
                RoleArn=os.environ['MEDIA_AWS_ROLE_ARN'], RoleSessionName='growthai-media',
                WebIdentityToken=token, DurationSeconds=3600)['Credentials']
        finally:
            sts.close()
        return boto3.client('s3', region_name=region, endpoint_url=endpoint, config=config,
                            aws_access_key_id=credentials['AccessKeyId'],
                            aws_secret_access_key=credentials['SecretAccessKey'],
                            aws_session_token=credentials['SessionToken'])
    if os.getenv('MEDIA_AWS_PROFILE') and os.getenv('VERCEL') != '1':
        return boto3.Session(profile_name=os.environ['MEDIA_AWS_PROFILE'], region_name=region).client('s3', endpoint_url=endpoint, config=config)
    if os.getenv('MEDIA_AWS_RUNTIME_ROLE') == '1' and os.getenv('AWS_LAMBDA_FUNCTION_NAME') and os.getenv('VERCEL') != '1':
        return boto3.client('s3', region_name=region, endpoint_url=endpoint, config=config)
    return boto3.client('s3', region_name=region, endpoint_url=endpoint, config=config,
                        aws_access_key_id=os.environ['MEDIA_AWS_ACCESS_KEY_ID'],
                        aws_secret_access_key=os.environ['MEDIA_AWS_SECRET_ACCESS_KEY'])


def request_client(request):
    """Create one client per request; no credentials or presigned URLs in logs."""
    from botocore.exceptions import BotoCoreError, ClientError
    try:
        if os.getenv('MEDIA_AWS_ROLE_ARN'):
            return s3_client(request.headers.get('x-vercel-oidc-token'))
        return s3_client()
    except (BotoCoreError, ClientError):
        raise HTTPException(503, 'AWS 저장소 인증에 실패했습니다. 서버의 역할 연결 설정을 확인해주세요.')


def signature(payload):
    return hmac.new(os.environ['MEDIA_SIGNING_SECRET'].encode(), payload.encode(), hashlib.sha256).hexdigest()


def owner(session):
    return hashlib.sha256(session.encode()).hexdigest()


def create_upload(batch, session, client=None, center_id=None):
    client = client if client is not None else s3_client()
    exam_id = uuid.uuid4().hex
    prefix = f'exams/{center_id}/{exam_id}' if center_id else f'exams/{exam_id}'
    records, uploads = [], []
    for file in batch.files:
        ext = PurePosixPath(file.name).suffix.lower()
        key = f'{prefix}/{uuid.uuid4().hex}{ext}'
        fields = {'Content-Type': TYPES[ext], 'x-amz-checksum-algorithm': 'SHA256',
                  'x-amz-checksum-sha256': file.sha256,
                  'x-amz-server-side-encryption': 'AES256', 'success_action_status': '204'}
        uploads.append(client.generate_presigned_post(
            Bucket=os.environ['MEDIA_S3_BUCKET'], Key=key, Fields=fields,
            Conditions=[{k: v} for k, v in fields.items()] + [['content-length-range', file.size, file.size]],
            ExpiresIn=UPLOAD_TTL))
        records.append({**file.model_dump(), 'key': key, 'content_type': TYPES[ext]})
    manifest = {'version': 1, 'exam_id': exam_id, 'owner': owner(session),
                'expires': int(time.time()) + TICKET_TTL, 'files': records, 'center_id': center_id}
    payload = base64.urlsafe_b64encode(json.dumps(manifest, separators=(',', ':')).encode()).decode()
    return {'ticket': payload + '.' + signature(payload), 'exam_id': exam_id,
            'uploads': uploads, 'upload_expires_in': UPLOAD_TTL, 'ticket_expires_in': TICKET_TTL}


def read_ticket(ticket, session, center_id=None):
    require_config()
    try:
        if len(ticket) > 24000:
            raise ValueError()
        payload, sig = ticket.split('.')
        if not hmac.compare_digest(sig, signature(payload)):
            raise ValueError()
        manifest = json.loads(base64.b64decode(payload, altchars=b'-_', validate=True))
        if manifest['version'] != 1 or manifest['owner'] != owner(session):
            raise ValueError()
        if not time.time() < manifest['expires'] <= time.time() + TICKET_TTL:
            raise ValueError()
        if manifest.get('center_id') != center_id:
            raise ValueError()
        UploadBatch(files=[{k: f[k] for k in ('name', 'size', 'group', 'sha256')} for f in manifest['files']])
        return manifest
    except (ValueError, KeyError, TypeError):
        raise HTTPException(403, '업로드 정보가 만료되었거나 현재 로그인과 일치하지 않습니다. 다시 업로드해주세요.')


def fetch_file(record, client=None):
    """Read only server-issued keys, enforce length/checksum and actual file signature."""
    from botocore.exceptions import BotoCoreError, ClientError
    try:
        client = client if client is not None else s3_client()
        obj = client.get_object(Bucket=os.environ['MEDIA_S3_BUCKET'], Key=record['key'])
        body = obj['Body']
        try:
            if obj['ContentLength'] != record['size'] or obj.get('ContentType') != record['content_type']:
                raise HTTPException(422, '업로드된 파일의 크기 또는 형식이 일치하지 않습니다.')
            raw = body.read(record['size'] + 1)
        finally:
            body.close()
    except (BotoCoreError, ClientError):
        raise HTTPException(502, '저장소에서 파일을 확인하지 못했습니다. 업로드를 다시 시도해주세요.')
    digest = base64.b64encode(hashlib.sha256(raw).digest()).decode()
    if len(raw) != record['size'] or not hmac.compare_digest(digest, record['sha256']):
        raise HTTPException(422, '파일 체크섬이 일치하지 않습니다. 다시 업로드해주세요.')
    kind = record['content_type']
    valid = {'image/png': raw.startswith(b'\x89PNG\r\n\x1a\n'),
             'image/jpeg': raw.startswith(b'\xff\xd8\xff'),
             'image/webp': raw[:4] == b'RIFF' and raw[8:12] == b'WEBP',
             'application/pdf': raw.startswith(b'%PDF-'),
             'text/plain': b'\x00' not in raw}
    if not valid.get(kind):
        raise HTTPException(422, '파일 내용이 확장자와 일치하지 않습니다.')
    return UploadFile(file=io.BytesIO(raw), filename=record['name'], size=len(raw))
