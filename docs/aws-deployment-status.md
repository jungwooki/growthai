# AWS 운영 배포 — 2026-09-26

- URL: https://z3mvzwqkz5y6thouemc6p6vgd40ocomx.lambda-url.ap-southeast-2.on.aws/
- 프로젝트: 616714047727, 리전: ap-southeast-2.
- Lambda: growthai, Python 3.12 / x86_64, 2048MB, 300초.
- 역할: growthai-lambda-runtime. exams/* 및 budget/* 읽기·쓰기,
  references/*와 runtime/growthai-config.json 읽기만 허용. 로그는 앱 로그 그룹에 한정.
- 로그 그룹: /aws/lambda/growthai, 보존 14일.
- 버킷: growthai-media-616714047727-aps2. 퍼블릭 접근 차단 유지.
- 배포 ZIP: deployments/growthai-20260926.zip. 최신 2열 화면과 근거 원본 11개 포함.
- 비밀 설정: runtime/growthai-config.json, SSE-S3 AES256 암호화 확인.
  Lambda 시작 시 실행 역할로 읽으며 허용한 5개 설정만 로드. 값은 문서·ZIP·로그에 포함하지 않음.
  변경 후 실행 환경을 재생성해야 적용됨. 예: Lambda 구성 갱신.
- 환경 설정: 비공개 직접 업로드 및 S3 월간 비용 원장 활성화,
  기본 예산 50,000원, 서버·저장소 월 예비비 10,000원.
- Function URL은 사용자 명시 승인으로 공개. 로그인·자료·센터/본부 권한은 앱에서 검증.
  공개 첫 화면 외 인증 없는 /api/status는 401 확인.
- /healthz 200, 첫 화면 200 확인.
- 로컬 Python 기존 92개와 런타임 설정 장애/허용키 검증 2개, JS 5개 통과.

## 남은 확인

- references/ 별도 사본 업로드 및 세 계정 실제 로그인·업로드 검증은 추가 승인 대기.
- 실제 AI 요청의 성공·과금·의학적 정확도는 아직 확인하지 않음.
- 기존 Vercel 사이트와 HAEON EMR 입구는 이 배포로 변경하지 않음.
- AWS 요금제 및 고급 기능 변경 없음. 월 5만 원은 추정 예산이지 청구 상한이 아님.

## 비용 저장소 최초 연결 오류 수정

- 신규 월 원장이 아직 없을 때, 실행 역할에 ListBucket이 없어 GetObject가
  NoSuchKey(404) 대신 AccessDenied(403)를 반환했다.
- growthai-runtime-scoped 역할 정책에 해당 버킷 한정 s3:ListBucket 추가.
  객체 내용 읽기/쓰기 범위는 기존대로 유지.
- 같은 실행 역할의 임시 비공개 Lambda로 실제 검증:
  없는 원장 NoSuchKey 응답, 조건부 PutObject, GetObject 읽기 모두 성공.
- 시험용 객체와 임시 Lambda는 검증 후 제거. 실제 월 원장 및 사용 기록은 변경하지 않음.
- IAM SimulatePrincipalPolicy는 조직 정책 판정 explicitDeny를 반환했으나,
  실제 동일 실행 역할의 S3 호출은 성공했다. 운영 검증 결과를 기준으로 기록함.
- 앱 로그인 후 화면 검증은 별도 승인 대기 상태로 유지.
