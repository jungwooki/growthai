import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
from backend import server
from backend.web_access import WebAccess

CREDENTIALS={'username':'clinician','password':'test-password-16-plus'}

@pytest.fixture
def hosted(monkeypatch):
 monkeypatch.setattr(server,'ACCESS',WebAccess(True,frozenset({'growth.example'}),**CREDENTIALS))
 return TestClient(server.app,base_url='https://growth.example')

def sign_in(client):
 return client.post('/api/auth/login',json=CREDENTIALS)

@pytest.mark.parametrize('path',['/api/library','/api/status','/api/sources/R01','/app.js'])
def test_hosted_routes_require_login(hosted,path):
 r=hosted.get(path)
 assert r.status_code==401 and 'www-authenticate' not in r.headers
 assert r.headers['cache-control']=='no-store'

@pytest.mark.parametrize('path',['/workspace','/workspace.html'])
def test_workspace_redirects_to_login(hosted,path):
 r=hosted.get(path,follow_redirects=False)
 assert r.status_code==303 and r.headers['location']=='/?login=required'

def test_hosted_login_cookie_and_https(hosted):
 response=sign_in(hosted)
 assert response.status_code==200
 cookie=response.headers['set-cookie']
 for flag in ['HttpOnly','Secure','SameSite=strict','Max-Age=28800']:
  assert flag in cookie
 assert CREDENTIALS['password'] not in cookie
 assert hosted.get('/api/status').json()['hosted'] is True
 assert hosted.get('/api/library').status_code==200
 assert hosted.get('/workspace').status_code==200
 assert hosted.get('http://growth.example/api/status').status_code==400
 assert hosted.get('/api/status',headers={'host':'other.example'}).status_code==400
 assert hosted.get('/.env').status_code==404
 assert hosted.get('/').headers['strict-transport-security']=='max-age=31536000'

def test_wrong_credentials_do_not_issue_cookie(hosted):
 for credentials in [{'username':'wrong','password':CREDENTIALS['password']},{'username':'clinician','password':'wrong'}]:
  response=hosted.post('/api/auth/login',json=credentials)
  assert response.status_code==401 and 'set-cookie' not in response.headers
  assert response.json()['detail']=='아이디 또는 비밀번호를 확인해주세요.'

def test_logout_clears_session(hosted):
 sign_in(hosted)
 result=hosted.post('/api/auth/logout',follow_redirects=False)
 assert result.status_code==200 and result.json()['redirect']=='/?logged_out=1'
 assert hosted.get('/api/status').status_code==401
 assert not hosted.cookies.get('growthai_session')

def test_tampered_expired_and_rotated_sessions(hosted,monkeypatch):
 import backend.web_access as policy
 token=server.ACCESS.issue_session()
 assert server.ACCESS.session_valid(token)
 assert not server.ACCESS.session_valid(token+'x')
 assert not server.ACCESS.session_valid('0.fake.invalid')
 rotated=WebAccess(True,server.ACCESS.hosts,'clinician','different-password-16-plus')
 assert not rotated.session_valid(token)
 now=policy.time.time()
 monkeypatch.setattr(policy.time,'time',lambda:now+8*60*60+1)
 assert not server.ACCESS.session_valid(token)
 hosted.cookies.set('growthai_session',token)
 assert hosted.get('/api/status').status_code==401

def test_health_exposes_no_details(hosted):
 assert hosted.get('/healthz').json()=={'status':'ok'}

def test_hosted_cross_site_rejected(hosted):
 for path in ['/api/auth/login','/api/auth/logout','/api/evaluate']:
  assert hosted.post(path,json=CREDENTIALS,headers={'origin':'https://other.example'}).status_code==403
  assert hosted.post(path,json=CREDENTIALS,headers={'sec-fetch-site':'cross-site'}).status_code==403

def test_same_origin_login_allowed(hosted):
 assert hosted.post('/api/auth/login',json=CREDENTIALS,headers={'origin':'https://growth.example'}).status_code==200

def test_missing_host_config_closed(monkeypatch):
 monkeypatch.setattr(server,'ACCESS',WebAccess(True,frozenset({'growth.example'}),'',''))
 client=TestClient(server.app,base_url='https://growth.example')
 assert client.get('/').status_code==200
 assert client.get('/workspace').status_code==503
 assert client.get('/api/status').status_code==503
 assert sign_in(client).status_code==503

def test_render_hostname_used(monkeypatch):
 monkeypatch.setenv('APP_ENV','production')
 monkeypatch.setenv('RENDER_EXTERNAL_HOSTNAME','example.onrender.com')
 monkeypatch.setenv('ALLOWED_HOSTS','custom.example')
 assert WebAccess.from_env().hosts==frozenset({'custom.example','example.onrender.com'})

def test_landing_is_public_but_workspace_and_data_are_private(hosted):
 for path in ['/','/index.html','/frontend/css/landing.css','/frontend/js/login.js','/frontend/assets/mps-symbol.png']:
  response=hosted.get(path)
  assert response.status_code==200 and 'www-authenticate' not in response.headers
 assert 'id="login-form"' in hosted.get('/').text
 assert 'assessment-form' not in hosted.get('/').text
 assert hosted.get('http://growth.example/').status_code==400
 assert hosted.get('/',headers={'host':'other.example'}).status_code==400
 assert hosted.get('/api/chart').status_code==401
 assert hosted.post('/api/evaluate').status_code==401

def test_configured_host_accepts_url_and_port(monkeypatch):
 monkeypatch.setenv('ALLOWED_HOSTS','https://growth.example/, localhost:8093, [::1]:8093')
 config=WebAccess.from_env()
 assert {'growth.example','localhost','::1'}<=config.hosts
 assert 'other.example' not in config.hosts

def test_vercel_enforces_login_and_exact_host(monkeypatch):
 monkeypatch.setenv('VERCEL','1');monkeypatch.setenv('APP_ENV','local')
 monkeypatch.setenv('VERCEL_PROJECT_PRODUCTION_URL','growthai-two.vercel.app')
 config=WebAccess.from_env()
 assert config.production and 'growthai-two.vercel.app' in config.hosts
 assert 'other.vercel.app' not in config.hosts
