import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
from backend import server
from backend.web_access import WebAccess

@pytest.fixture
def hosted(monkeypatch):
 monkeypatch.setattr(server,'ACCESS',WebAccess(True,frozenset({'growth.example'}),'clinician','test-password-16-plus'))
 return TestClient(server.app,base_url='https://growth.example')

@pytest.mark.parametrize('path',['/','/api/library','/api/status','/api/sources/R01','/app.js'])
def test_hosted_routes_require_login(hosted,path):
 r=hosted.get(path)
 assert r.status_code==401 and r.headers['www-authenticate'].startswith('Basic')
 assert r.headers['cache-control']=='no-store'

def test_hosted_login_and_https(hosted):
 auth=('clinician','test-password-16-plus')
 assert hosted.get('/api/status',auth=auth).json()['hosted'] is True
 assert hosted.get('/api/library',auth=auth).status_code==200
 assert hosted.get('/api/status',auth=('clinician','incorrect')).status_code==401
 assert hosted.get('http://growth.example/api/status',auth=auth).status_code==400
 assert hosted.get('/api/status',auth=auth,headers={'host':'other.example'}).status_code==400
 assert hosted.get('/.env',auth=auth).status_code==404
 assert hosted.get('/',auth=auth).headers['strict-transport-security']=='max-age=31536000'

def test_health_exposes_no_details(hosted):
 assert hosted.get('/healthz').json()=={'status':'ok'}

def test_hosted_cross_site_rejected(hosted):
 assert hosted.post('/api/evaluate',auth=('clinician','test-password-16-plus'),headers={'origin':'https://other.example'}).status_code==403
 assert hosted.post('/api/evaluate',auth=('clinician','test-password-16-plus'),headers={'sec-fetch-site':'cross-site'}).status_code==403

def test_missing_host_config_closed(monkeypatch):
 monkeypatch.setattr(server,'ACCESS',WebAccess(True,frozenset({'growth.example'}),'',''))
 assert TestClient(server.app,base_url='https://growth.example').get('/').status_code==503

def test_render_hostname_used(monkeypatch):
 monkeypatch.setenv('APP_ENV','production')
 monkeypatch.setenv('RENDER_EXTERNAL_HOSTNAME','example.onrender.com')
 monkeypatch.setenv('ALLOWED_HOSTS','custom.example')
 config=WebAccess.from_env()
 assert config.hosts==frozenset({'custom.example','example.onrender.com'})

def test_auth_malformed_is_safe(hosted):
 for auth in ['broken','Basic ~~~','Bearer anything','Basic YQ==']:
  assert hosted.get('/',headers={'authorization':auth}).status_code==401
