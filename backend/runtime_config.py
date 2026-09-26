"""Load allowlisted production settings from a private, encrypted S3 object.

Only the Lambda execution role can read this object; never log its contents.
"""
import json
import os

KEYS = frozenset({'OPENAI_API_KEY', 'OPENAI_MODEL', 'APP_CENTER_AUTH_JSON',
                  'APP_SESSION_SECRET', 'MEDIA_SIGNING_SECRET'})


def load_runtime_config():
    bucket = os.getenv('RUNTIME_CONFIG_BUCKET')
    key = os.getenv('RUNTIME_CONFIG_KEY')
    if not bucket and not key:
        return
    if not bucket or not key or os.getenv('APP_ENV') != 'production':
        raise RuntimeError('Invalid runtime configuration location')
    import boto3
    client = boto3.client('s3', region_name=os.environ['MEDIA_S3_REGION'])
    try:
        with client.get_object(Bucket=bucket, Key=key)['Body'] as body:
            raw = body.read(32769)
        if len(raw) > 32768:
            raise RuntimeError('Runtime configuration exceeds size limit')
        config = json.loads(raw)
        if not isinstance(config, dict) or set(config) != KEYS:
            raise RuntimeError('Invalid runtime configuration keys')
        if any(not isinstance(value, str) or not value for value in config.values()):
            raise RuntimeError('Missing runtime configuration values')
        os.environ.update(config)
    finally:
        client.close()
