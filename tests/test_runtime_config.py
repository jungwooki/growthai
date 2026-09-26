from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io
import json
from unittest.mock import Mock
import pytest
from backend.runtime_config import KEYS, load_runtime_config


def test_runtime_config_rejects_unexpected_keys_without_environment_changes(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('RUNTIME_CONFIG_BUCKET', 'private-test-bucket')
    monkeypatch.setenv('RUNTIME_CONFIG_KEY', 'runtime/config.json')
    monkeypatch.setenv('MEDIA_S3_REGION', 'ap-southeast-2')
    monkeypatch.setenv('OPENAI_API_KEY', 'unchanged')
    client = Mock()
    payload = {key: 'test-value' for key in KEYS}
    payload['AWS_ACCESS_KEY_ID'] = 'not-allowed'
    body = io.BytesIO(json.dumps(payload).encode())
    client.get_object.return_value = {'Body': body}
    monkeypatch.setattr('boto3.client', lambda *args, **kwargs: client)
    with pytest.raises(RuntimeError, match='keys'):
        load_runtime_config()
    import os
    assert os.environ['OPENAI_API_KEY'] == 'unchanged'
    assert body.closed
    client.close.assert_called_once()


def test_runtime_config_closes_client_when_store_unavailable(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('RUNTIME_CONFIG_BUCKET', 'private-test-bucket')
    monkeypatch.setenv('RUNTIME_CONFIG_KEY', 'runtime/config.json')
    monkeypatch.setenv('MEDIA_S3_REGION', 'ap-southeast-2')
    client = Mock()
    client.get_object.side_effect = RuntimeError('unavailable')
    monkeypatch.setattr('boto3.client', lambda *args, **kwargs: client)
    with pytest.raises(RuntimeError, match='unavailable'):
        load_runtime_config()
    client.close.assert_called_once()
