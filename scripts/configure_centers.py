"""Create a local secret env file interactively; never deploy or print credentials."""
import getpass
import json
import os
import secrets
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.centers import DEFAULT_CENTERS, hash_password

def main():
    target=Path(__file__).resolve().parents[1]/'.env.centers.local'
    if target.exists():
        raise SystemExit('기존 .env.centers.local 파일을 덮어쓰지 않습니다.')
    users=[]
    for username,role,center_id in [('jrgoldenage','headquarters',None),('ljw0001','center','seoul-rnd'),('dongtan','center','gyeonggi-dongtan')]:
        print(f'{username}: 16자 이상 비밀번호를 설정합니다. 입력은 화면에 표시되지 않습니다.')
        password=getpass.getpass('비밀번호: ')
        if password!=getpass.getpass('다시 입력: '):
            raise SystemExit('비밀번호가 일치하지 않습니다. 저장하지 않았습니다.')
        users.append(dict(username=username,role=role,center_id=center_id,password_hash=hash_password(password)))
    data=json.dumps(dict(centers=DEFAULT_CENTERS,users=users),ensure_ascii=False,separators=(',',':'))
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf8') as output:
        output.write("APP_CENTER_AUTH_JSON='"+data+"'\nAPP_SESSION_SECRET="+secrets.token_urlsafe(48)+'\n')
    print('로컬 .env.centers.local 저장 완료. 배포 환경변수 연결은 별도입니다. 파일 내용을 공유하지 마세요.')

if __name__=='__main__':main()
