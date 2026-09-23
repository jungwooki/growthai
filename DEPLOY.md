# GitHub → Vercel 배포 및 오류 해결

2026-09-24 점검: `https://growthai-two.vercel.app/api/status`에서 HTTP 503과
`웹 서비스 접속 설정을 완료해주세요.` 응답을 확인했습니다.
이는 Python 서버가 실행된 뒤 접속 설정 검사에서 차단된 상태입니다.
화면의 index 파일만 바꾸거나 재배포만 반복해도 환경변수가 빠져 있으면 해결되지 않습니다.

## 현재 주소에서 필요한 설정

Vercel → growthai 프로젝트 → Settings → Environment Variables에서 아래를 설정합니다.
Production에 반드시 적용하고, Preview를 사용할 경우 Preview에도 설정합니다.

| 이름 | 값 |
| --- | --- |
| `APP_ENV` | `production` |
| `ALLOWED_HOSTS` | `growthai-two.vercel.app` (추가 도메인은 쉼표로 구분) |
| `APP_USERNAME` | 직접 정한 의료진 로그인 아이디 |
| `APP_PASSWORD` | 직접 정한 **16자 이상** 로그인 비밀번호 |
| `OPENAI_API_KEY` | AI 사용 시 서버용 API 키 |
| `OPENAI_MODEL` | `gpt-4.1` |

API 키와 비밀번호는 GitHub 또는 HTML에 넣지 않습니다.
설정 저장 후 Deployments에서 최신 코드로 **Redeploy**합니다. 환경변수 수정은 기존 배포에 소급 적용되지 않습니다.
`/` 접속 시 브라우저 로그인 창이 나오면 APP_USERNAME/APP_PASSWORD를 입력합니다.
OPENAI_API_KEY가 없어도 기본 수치 비교는 가능합니다.

## 프로젝트 구조와 빌드 설정

별도 저장소 `jungwooki/growthai`는 `server.py`, `index.html`, `requirements.txt`,
`vercel.json`이 저장소 최상단에 있습니다. Vercel Root Directory는 저장소 루트(`.`)입니다.
상위 작업공간 전체를 연결한 경우에만 Root Directory를 `growthai`로 지정합니다.

- Framework Preset: **FastAPI** (`vercel.json`에 명시).
- Build Command / Install Command / Output Directory: 기존 수동 Override를 끄고 기본값 사용.
- `pyproject.toml`의 진입점은 `server:app`, Python 버전은 `.python-version`의 3.12.
- `server.py` → `backend/server.py`가 `/`, `/index.html`, `/api/*`를 제공.
- `frontend/`는 CSS·JS·이미지. `data/*.json`은 계산·검색 기준 데이터.
- 정적 SPA용 `/(.*) → /index.html` rewrite는 사용하지 않습니다.
- 함수 실행시간은 300초로 설정했습니다. 실제 플랜·프로젝트 설정에서 적용 여부를 확인합니다.

## 근거 원본과 업로드 범위

`data/sources/`의 원본 11개(약 44MB)는 `.gitignore`에서 제외되어 있으므로
**GitHub 연동 배포에는 원본이 없습니다.** 현재 수정본은 누락 여부를 표시하고,
기본 계산·텍스트 검색은 계속 제공하며 AI 영상 비교는 원본이 준비되기 전 실행하지 않습니다.
원본을 건너뛰고 AI가 비교한 것처럼 결과를 만들지 않습니다.

원본은 승인된 비공개 배포 번들 또는 비공개 저장소 연동으로 제공해야 합니다.
기존 `scripts/package_web.py`로 만드는 로컬 비공개 전달 ZIP에는 원본이 포함됩니다.
이 ZIP을 생성하는 것만으로 GitHub 연동 배포에 원본이 추가되지는 않습니다.
현재 비공개 객체 저장소 연동은 구현되지 않았습니다.

Vercel 함수의 4.5MB 요청·응답 제한 때문에 이 앱의 첨부 합계를 **4MB**로 제한했습니다
(폼 데이터 여유분 확보). 로컬/Render는 기존 120MB 제한을 유지합니다.
4MB가 넘는 근거 원본 다운로드에는 안내 오류를 반환합니다.
많은 고해상도 사진·큰 PDF를 그대로 다루려면 기존 Render/Docker 배포를 사용하거나
인증된 비공개 객체 저장소 직접 업로드를 추가해야 합니다.

## 확인 순서

1. `/healthz`: HTTP 200, `{"status":"ok"}`.
2. `/`: 로그인 창 → 입력 후 워크스페이스.
3. `/api/status`: 로그인 상태에서 JSON. 원본 누락은 `missing_sources` 확인.
4. 가상 예시 → AI 끄기 → 기본 수치 확인 → 성장 곡선.
5. 원본과 API 키를 모두 준비한 후에만 AI 검증.

코드 자동 테스트와 로컬 Chrome 검증은 완료했습니다. Vercel의 환경변수 변경,
GitHub push 및 새 배포는 이 로컬 수정 작업에서 실행하지 않았습니다.

공식 문서: [FastAPI 배포](https://vercel.com/docs/frameworks/backend/fastapi),
[함수 제한](https://vercel.com/docs/functions/limitations),
[Python 런타임](https://vercel.com/docs/functions/runtimes/python).

---

# Render / Docker 대안

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
