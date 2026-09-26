# AWS 비공개 업로드 연결 기록 — 2026-09-26

## 완료된 설정

- CLI 프로필: `growthai`, 리전: `ap-southeast-2`.
- S3 버킷: `growthai-media-616714047727-aps2`.
- 퍼블릭 접근 차단 4개 모두 활성화, BucketOwnerEnforced, SSE-S3 AES256.
- HTTP 접근 거부 정책 적용. 버킷 정책 공개 상태: false.
- CORS: `https://growthai-two.vercel.app`의 POST만 허용.
- 원본 경로: `exams/<무작위 검사 ID>/<무작위 파일 ID>.<확장자>`.
- 자동 삭제 정책 없음. 실제 운영을 위한 버킷은 유지하며 저장·요청·전송 비용이 발생할 수 있습니다.
- Vercel 로그인 및 프로젝트 연결 확인. 팀 `haeons-projects`, 프로젝트 `growthai`.

## 실제 검증

`tests/live_s3_upload.py`를 로컬 AWS 프로필로 실행했습니다. 자동 테스트에서는 실행되지 않습니다.
합성 PNG 12개, 총 4,813,332바이트를 실제 S3에 직접 전송하고 앱의 평가 경로에서 모두 읽었습니다.
AI 호출 없이 12개 결과의 ID·부위·체크섬을 검증했습니다.
운영 출처의 CORS 허용, 다른 출처 차단, 익명 원본 접근 차단, 변조 및 초과 크기 업로드 차단도 통과했습니다.
발급된 검사 경로의 테스트 객체 12개만 삭제했습니다.

로컬 AWS 브라우저 로그인에는 `botocore[crt]`가 필요합니다.
S3 서명 URL은 지역 엔드포인트를 명시합니다. 전역 엔드포인트의 CORS 동작 차이를 실제 검증에서 발견해 수정했습니다.

## 남은 연결과 정책 제약

AWS의 새로운 경험 관리 SCP에서 `iam:*Provider*`를 거부합니다.
실제 `iam:ListOpenIDConnectProviders` 요청도 명시적으로 거부되었습니다.
따라서 이 정책 상태에서 Vercel용 OIDC 제공자를 생성할 수 없습니다.
제공자·앱 역할은 생성하지 않았으며, Vercel 업로드 환경변수 변경과 운영 배포도 수행하지 않았습니다.

[AWS 관리 정책](https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html)과
[고급 기능 활성화 안내](https://docs.aws.amazon.com/accounts/latest/reference/activate-advanced-features.html)를 확인했습니다.
고급 기능 전환은 되돌릴 수 없고 기존 지출 한도가 제거되므로 사용자가 결정해야 합니다.

Vercel 유지 시 준비된 연결 계획:

- OIDC issuer: `https://oidc.vercel.com/haeons-projects`.
- audience: `https://vercel.com/haeons-projects`.
- subject: `owner:haeons-projects:project:growthai:environment:production`.
- 앱 권한 범위: 위 버킷의 `exams/*` 원본 쓰기·읽기.
- Production 환경변수: `MEDIA_STORAGE=s3`, 위 버킷과 리전,
  `MEDIA_AWS_ROLE_ARN`, 새 무작위 `MEDIA_SIGNING_SECRET`.
- 앱은 매 요청의 `x-vercel-oidc-token`으로 임시 자격 증명을 받고 종료 시 연결을 닫습니다.
- 로컬에서만 `MEDIA_AWS_PROFILE=growthai`를 지원합니다. 브라우저 로그인 자격 증명은 Vercel에 복사하지 않습니다.

IAM Policy Autopilot 소스 분석은 실행했으나, presigned POST 권한을 자동으로 식별하지 못하고 불필요한 읽기 권한도 제안했습니다.
해당 결과를 배포하지 않았습니다. 정책 제약 해결 후 실제 PutObject/GetObject 범위로 검토·검증해야 합니다.

현재 지원 범위는 이미지 최대 12개, 파일당 20MiB, 총 240MiB입니다.
영상·DICOM 및 원본 전체 해상도를 AI에 입력하는 기능은 아직 구현하지 않았습니다.
