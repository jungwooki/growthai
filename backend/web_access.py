"""Local development and authenticated HTTPS hosting policies."""
import base64
import os
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse
from fastapi.responses import JSONResponse

@dataclass(frozen=True)
class WebAccess:
    production: bool
    hosts: frozenset
    username: str
    password: str

    @classmethod
    def from_env(cls):
        production=os.getenv('APP_ENV','local')=='production'
        hosts=set(filter(None,(s.strip().lower() for s in os.getenv('ALLOWED_HOSTS','').split(','))))
        render_host=os.getenv('RENDER_EXTERNAL_HOSTNAME','').strip().lower()
        if render_host:hosts.add(render_host)
        if not production:hosts|={'127.0.0.1','localhost','testserver'}
        return cls(production,frozenset(hosts),os.getenv('APP_USERNAME',''),os.getenv('APP_PASSWORD',''))

    def check(self,request):
        if self.production and (not self.hosts or not self.username or len(self.password)<16):
            return JSONResponse({'detail':'웹 서비스 접속 설정을 완료해주세요.'},503)
        if request.url.hostname not in self.hosts:
            return JSONResponse({'detail':'허용되지 않은 접속 주소입니다.'},400)
        # No document, key, or model information is exposed by the health route.
        if request.url.path=='/healthz' and request.method in {'GET','HEAD'}:
            return None
        if self.production and request.url.scheme!='https':
            return JSONResponse({'detail':'HTTPS 주소로 접속해주세요.'},400)
        if self.production:
            valid=False
            try:
                scheme,token=request.headers.get('authorization','').split(' ',1)
                username,password=base64.b64decode(token,validate=True).decode('utf-8').split(':',1)
                valid=(scheme.lower()=='basic' and secrets.compare_digest(username.encode(),self.username.encode()) and secrets.compare_digest(password.encode(),self.password.encode()))
            except (ValueError,UnicodeError):pass
            if not valid:
                return JSONResponse({'detail':'의료진 계정으로 로그인해주세요.'},401,headers={'WWW-Authenticate':'Basic realm="MPS Growth", charset="UTF-8"'})
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
        return None
