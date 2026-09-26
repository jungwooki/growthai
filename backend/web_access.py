"""Local development and authenticated HTTPS hosting policies."""
import hashlib
import hmac
import time
import os
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse
from . import centers
from fastapi import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse

def normalize_host(value):
    value=value.strip().lower()
    if not value:return None
    if value=='::1':return value
    try:
        parsed=urlparse(value if '://' in value else '//'+value)
        if parsed.username or parsed.password:return None
        return parsed.hostname
    except ValueError:return None

@dataclass(frozen=True)
class WebAccess:
    production: bool
    hosts: frozenset
    username: str
    password: str

    @classmethod
    def from_env(cls):
        production=os.getenv('APP_ENV','local')=='production' or os.getenv('VERCEL')=='1'
        hosts=set(filter(None,(normalize_host(s) for s in os.getenv('ALLOWED_HOSTS','').split(','))))
        render_host=os.getenv('RENDER_EXTERNAL_HOSTNAME','').strip().lower()
        if render_host:hosts.add(normalize_host(render_host))
        if os.getenv('VERCEL')=='1':
            for key in ['VERCEL_URL','VERCEL_PROJECT_PRODUCTION_URL','VERCEL_BRANCH_URL']:
                host=normalize_host(os.getenv(key,''))
                if host:hosts.add(host)
        if not production:hosts|={'127.0.0.1','localhost','::1','testserver'}
        return cls(production,frozenset(hosts),os.getenv('APP_USERNAME',''),os.getenv('APP_PASSWORD',''))

    @property
    def configured(self):
        return bool(self.username) and len(self.password)>=16

    def credentials_match(self,username,password):
        return (self.configured and secrets.compare_digest(username.encode(),self.username.encode())
                and secrets.compare_digest(password.encode(),self.password.encode()))

    def _signature(self,payload):
        # Credential rotation also invalidates previously issued sessions.
        key=hashlib.sha256(('growthai-session-v1\0'+self.username+'\0'+self.password).encode()).digest()
        return hmac.new(key,payload.encode(),hashlib.sha256).hexdigest()

    def issue_session(self):
        payload=f'{int(time.time())+8*60*60}.{secrets.token_hex(24)}'
        return payload+'.'+self._signature(payload)

    def session_valid(self,token):
        if not self.configured or not token or len(token)>256:return False
        try:
            expiry,nonce,signature=token.split('.')
            remaining=int(expiry)-time.time()
            return (0<remaining<=8*60*60 and len(nonce)==48
                    and secrets.compare_digest(signature,self._signature(expiry+'.'+nonce)))
        except (ValueError,TypeError,UnicodeError):return False

    def check(self,request):
        if self.production and not self.hosts:
            return JSONResponse({'detail':'웹 서비스 접속 설정을 완료해주세요. APP_USERNAME, 16자 이상 APP_PASSWORD, ALLOWED_HOSTS(실제 배포 도메인)를 환경변수에 설정하고 재배포해주세요.'},503)
        if request.url.hostname not in self.hosts:
            message=('배포 주소를 ALLOWED_HOSTS에 등록하고 다시 배포해주세요.' if self.production else '이 Mac에서는 http://127.0.0.1:8093 으로 접속해주세요. 다른 주소는 ALLOWED_HOSTS에 등록해야 합니다.')
            return JSONResponse({'detail':'허용되지 않은 접속 주소입니다. '+message},400)
        # No document, key, or model information is exposed by the health route.
        if request.url.path=='/healthz' and request.method in {'GET','HEAD'}:
            return None
        if self.production and request.url.scheme!='https':
            return JSONResponse({'detail':'HTTPS 주소로 접속해주세요.'},400)
        if request.method in {'POST','PUT','PATCH','DELETE'}:
            origin=request.headers.get('origin')
            if origin and origin!=f'{request.url.scheme}://{request.headers.get("host")}':
                return JSONResponse({'detail':'동일한 앱에서만 요청할 수 있습니다.'},403)
            if request.headers.get('sec-fetch-site')=='cross-site':
                return JSONResponse({'detail':'외부 페이지에서 요청할 수 없습니다.'},403)
        try:
            length=int(request.headers.get('content-length','0'))
            if length<0:raise ValueError()
        except ValueError:
            return JSONResponse({'detail':'잘못된 요청 크기입니다.'},400)
        if length>125*1024*1024:
            return JSONResponse({'detail':'전체 업로드는 120MB 이하로 줄여주세요.'},413)
        if (os.getenv('VERCEL')=='1' or os.getenv('AWS_LAMBDA_FUNCTION_NAME')) and length>4_400_000:
            return JSONResponse({'detail':'이 배포에서는 첨부 합계를 4MB 이하로 줄여주세요.'},413)
        if request.method in {'GET','HEAD'} and request.url.path in {
            '/', '/index.html', '/frontend/css/landing.css', '/frontend/js/login.js',
            '/frontend/assets/mps-symbol.png'
        }:
            return None
        if request.url.path in {'/api/auth/login','/api/auth/logout'} and request.method=='POST':
            if length>4096:return JSONResponse({'detail':'로그인 요청이 너무 큽니다.'},413)
            return None
        if centers.enabled():
            try:
                principal=centers.resolve(request.cookies.get('growthai_session'))
            except HTTPException as error:
                return JSONResponse({'detail':error.detail},error.status_code)
            if not principal:
                if request.url.path in {'/workspace','/workspace/','/workspace.html','/headquarters'}:
                    return RedirectResponse('/?login=required',status_code=303)
                return JSONResponse({'detail':'센터 또는 본부 계정으로 로그인해주세요.'},401)
            request.state.principal=principal
            path=request.url.path
            if principal['role']=='center' and (path=='/headquarters' or path=='/api/budget/approve'):
                return JSONResponse({'detail':'MPS 본부 계정으로 이용해주세요.'},403)
            if principal['role']=='headquarters' and not (path.startswith('/frontend/') or path in {'/headquarters','/api/auth/me','/api/usage/monthly','/api/budget','/api/budget/approve'}):
                return JSONResponse({'detail':'본부 계정은 사용량 관리 화면을 이용해주세요.'},403)
            return None
        if self.production or self.username or self.password:
            if not self.configured:
                return JSONResponse({'detail':'의료진 로그인 설정이 필요합니다. APP_USERNAME과 16자 이상 APP_PASSWORD를 설정하고 재배포해주세요.'},503)
            if not self.session_valid(request.cookies.get('growthai_session')):
                if request.url.path in {'/workspace','/workspace/','/workspace.html'} and request.method in {'GET','HEAD'}:
                    return RedirectResponse('/?login=required',status_code=303)
                return JSONResponse({'detail':'로그인이 필요하거나 만료되었습니다. 첫 화면에서 다시 로그인해주세요.'},401)
        return None
