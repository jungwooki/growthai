# 별도 웹주소 배포

현재 상태: 웹 호스팅용 코드·접속 인증·배포 파일 준비. 실제 호스팅 배포와 주소 발급은 아직 하지 않았습니다. 기존 로컬 서버는 그대로 사용할 수 있습니다.

## 구조

브라우저 → HTTPS 웹주소 → Python 웹 서버 → OpenAI API

화면과 API를 같은 서버에서 제공합니다. 로컬 PC를 계속 켜두지 않아도 이용할 수 있는 서버 배포 방식입니다. 정적 HTML 호스팅만으로는 AI 서버가 실행되지 않습니다. API 키는 브라우저나 Git에 넣지 않습니다.

## Render에 배포하는 경우

1. `artifacts/mps-growth-web.zip`을 별도 폴더에 압축 해제합니다. 이 파일은 코드와 제공 근거 원본 11개를 포함하며 **API 키·.env·검진자료·테스트 결과는 제외**합니다. 새 비공개 저장소를 사용하세요. 기존 공개 사이트 저장소에 그대로 올리지 마세요.
2. 비공개 GitHub 저장소에 압축 해제한 내용을 넣고 Render 계정에서 해당 저장소를 연결합니다. 소스 및 근거자료가 GitHub와 Render로 전송됩니다. 아직 자동 업로드하지 않았습니다.
3. Render에서 Blueprint로 루트의 `render.yaml`을 선택하거나 Web Service / Docker로 생성합니다. 준비한 무료 플랜은 기능 확인용이며 운영 전 가용 자원과 처리량을 점검하세요.
4. 환경변수를 입력합니다.

| 이름 | 값 |
| --- | --- |
| `OPENAI_API_KEY` | 사용자의 OpenAI 키. Render 환경변수로 입력 |
| `OPENAI_MODEL` | `gpt-4.1` (기본값) |
| `APP_ENV` | `production` |
| `APP_USERNAME` | 의료진 접속 계정 |
| `APP_PASSWORD` | 최소 16자 이상의 별도 접속 비밀번호 |
| `TRUSTED_PROXY_IPS` | Render 프록시 뒤에서는 `*` |

5. 배포가 완료되면 Render가 발급한 `https://…onrender.com` 주소에 접속합니다. 브라우저 로그인 창에서 위 의료진 계정과 비밀번호를 입력합니다. **예시 주소를 이미 발급된 주소로 사용하지 마세요.**
6. 가상 예시로 기본 평가를 확인합니다. 근거자료의 OpenAI 전송을 승인한 후 AI 옵션과 전송 확인을 선택하여 전체 평가를 검증합니다.

Render의 `RENDER_EXTERNAL_HOSTNAME`을 읽어 허용 도메인을 설정합니다. 다른 서버나 사용자 도메인에서는 `ALLOWED_HOSTS=실제도메인`을 설정합니다. HTTPS는 호스팅 서비스/리버스 프록시가 종료하고 서버에 프로토콜을 전달해야 합니다. `TRUSTED_PROXY_IPS=*`는 외부 요청이 반드시 신뢰하는 프록시를 경유하는 플랫폼에서만 사용하고 일반 서버에서는 실제 프록시 주소를 지정하세요.

공개 접속 시 의료진 인증이 필요합니다. 원본 열기·근거 검색·평가 API에도 같은 인증을 적용합니다. 인증 없는 `/healthz`는 상태만 반환합니다. 호스트·계정·16자 이상 비밀번호 설정이 누락되면 서비스는 503으로 접근을 막습니다. 운영자는 개인별 계정/감사기록이 필요한 경우 별도 인증 체계로 확장해야 합니다. 현재는 단일 의료진 계정의 소규모 검토용입니다.

## 일반 Docker 서버

Docker가 설치된 환경에서 이 폴더를 빌드 컨텍스트로 사용합니다.

```sh
docker build -t mps-growth .
# 호스팅 환경변수/비밀 저장소에서 키·도메인·계정 설정 후 실행
# 8000 포트는 HTTPS 리버스 프록시로만 노출
docker run --rm -p 127.0.0.1:8000:8000 --env-file /secure/path/growth-runtime.env mps-growth
```

이 작업 환경에는 Docker가 없어 실제 컨테이너 빌드는 미검증입니다. Python 서버 테스트로 인증·허용 도메인·HTTPS 요구·API 동작을 검증했습니다. 배포 플랜 생성, 외부 저장소 업로드, 호스팅 비용 발생은 아직 수행하지 않았습니다.

공식 참고: [Render FastAPI 배포](https://render.com/docs/deploy-fastapi), [Blueprint 구성](https://render.com/docs/blueprint-spec).
