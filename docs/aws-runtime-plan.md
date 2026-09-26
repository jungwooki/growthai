# AWS 운영 전환 준비 — 2026-09-26

## 제안하는 구성

기존 Vercel 주소 대신 ap-southeast-2의 Lambda Function URL에서 FastAPI와 화면을 함께 제공합니다.
기존 비공개 S3 버킷을 사용하며 Lambda 실행 역할로 접근합니다.
이 구성은 Vercel Pro 기본요금과 외부 OIDC 제공자 생성이 필요하지 않습니다.
고급 기능 전환과 요금제 변경은 하지 않습니다. AWS는 사용량 과금이며 정액제나 절대 청구 상한이 아닙니다.

현재 AWS CLI에서 Paid/Active 상태, Lambda 목록 조회, 동시 실행 한도 10을 확인했습니다.
역할 생성 및 Function URL 생성은 실제 배포 전 검증해야 합니다. 조회 성공만으로 배포 권한까지 검증된 것은 아닙니다.

## 준비된 코드와 산출물

- FastAPI Lambda 어댑터: `backend/lambda_entry.handler` (Mangum 0.19.0).
- Python 3.12 / x86_64 Linux 의존성 및 참고자료를 포함한 비공개 ZIP:
  `artifacts/growthai-lambda.zip`.
- 생성 명령: `python scripts/build_lambda.py --uv <uv 실행파일>`.
- 잠금 파일 기준 의존성, 명시적 앱 파일 목록만 포함합니다.
  환경변수 파일·AWS/Vercel 로그인 정보·테스트 환자 자료는 포함하지 않습니다.
- 4MB 초과 참고 원본은 로그인 검증 후 S3의 `references/<자료ID>.<확장자>`에 대한
  60초 다운로드 URL로 제공합니다. 배포 시 manifest의 참고자료를 해당 경로에 설치해야 합니다.
- 환자 원본은 기존 `exams/*` 직접 업로드를 유지합니다.

## 월 5만 원 의사결정 기능

`BUDGET_STORAGE=s3`로 켜며, `budget/YYYY-MM.json`에 환자 정보 없이 비용 기록을 저장합니다.
파일 수정 충돌을 방지하는 조건부 쓰기로 동시 요청 및 재시도 중복 정산을 처리합니다.
한국 시간 기준 매월 기본 예산 50,000원으로 시작합니다.

- 결과지 전사와 초음파·종합 판독의 실제 응답 토큰을 별도로 기록합니다.
- GPT-4.1 단가와 환산 가정(1달러 1,500원, 세금 계수 1.10)으로 AI 추정액을 계산합니다.
  캐시 할인 토큰도 반영합니다. 이 환율은 실시간 시세가 아닙니다.
- 서버·저장소 월 예비비 기본 10,000원을 더합니다. 실제 AWS 청구액 조회 기능이 아닙니다.
- 70%, 90%에서 앱 화면에 안내합니다. 이메일·문자·카카오 알림은 발송하지 않습니다.
- AI 호출 전에 보수적인 요청 예비금을 확보합니다. 잔여 예산보다 크면 요청을 보내기 전에
  추가 총 예산 승인 또는 보류를 선택하게 합니다. 사이트 전체를 자동 중단하거나 파일을 삭제하지 않습니다.
- 사용자 승인 후에도 AI 호출은 자동 재실행하지 않습니다. 다시 판독 요청을 눌러야 합니다.
- 실제 사용량이 확인되면 예비금을 실제 토큰 기반 추정액으로 정산합니다.
  실패·시간초과·사용량 없는 응답의 예비금은 확인 대기로 남깁니다.
  현재 별도 청구 대조·미확정 요청 수동 정산 화면은 없습니다.
- 추가 승인은 해당 월에만 적용되며 기록됩니다. 다음 달 기본 예산은 그대로입니다.
- 비용 저장소 장애 또는 미등록 모델 단가에서는 비용 관리가 켜진 유료 AI 요청을 진행하지 않습니다.

이미 진행 중인 요청, 누적 S3 저장료, 외부 앱의 API 사용, 환율·세금 변동까지 차단하는 기능이 아닙니다.
따라서 월 5만 원은 운영 목표이며 절대 청구 상한으로 표시하지 않습니다.

## 배포 시 설정

- 리전 ap-southeast-2, Python 3.12, x86_64, 메모리 초기 2048MB, 제한시간 300초 후보.
- 실행 역할은 `exams/*`, `budget/*` 읽기·쓰기와 `references/*` 읽기에 한정해 최종 검증.
- IAM Policy Autopilot을 실제 소스로 실행했습니다:

  `uvx iam-policy-autopilot@latest generate-policies backend/media_storage.py backend/budget.py backend/server.py --service-hints s3 --region ap-southeast-2 --account 616714047727 --pretty`

  자동 결과에는 광범위한 버킷·KMS·ACL 권한이 포함돼 그대로 적용하지 않았습니다.
- 장기 AWS 키 대신 `MEDIA_AWS_RUNTIME_ROLE=1` 사용.
- APP_ENV=production, APP_USERNAME, APP_PASSWORD, 정확한 ALLOWED_HOSTS,
  OPENAI_API_KEY, MEDIA_SIGNING_SECRET과 S3 설정을 비공개로 설치.
- 새 URL은 공개 로그인 진입점이지만 자료·API는 앱 로그인으로 보호.
  Function URL의 NONE 인증을 쓸 경우 AWS 공식 안내의 두 호출 권한을 모두 검토해야 합니다.
- 원본 S3 CORS에 새 사이트 출처를 추가. 기존 출처 제거는 전환 확인 뒤 수행.
- 사용량 로그 보존 기간과 동시 실행 제한을 실제 프로젝트 한도에 맞춰 설정.

## 현재 상태

코드·로컬 배포 ZIP·합성 테스트까지 완료했습니다.
Lambda 실행 역할·함수·새 접속 주소는 아직 생성하지 않았고, 운영 환경변수나 기존 Vercel 배포를 변경하지 않았습니다.
실제 Lambda/Linux 실행, 권한·CORS·로그인과 대표 사례의 유료 AI 호출 검증이 남았습니다.
새 사이트로 운영할지 결정한 뒤 실제 배포를 진행할 수 있습니다.

참고: [Lambda URL](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html),
[Lambda 한도](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html),
[S3 조건부 쓰기](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html),
[GPT-4.1 단가](https://developers.openai.com/api/docs/models/gpt-4.1).
