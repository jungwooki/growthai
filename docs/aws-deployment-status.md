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

- references/ 원본 연결은 아래 후속 작업에서 완료. 세 계정 실제 로그인·업로드 검증은 미실시.
- 실제 AI 요청 성공은 아래 가상자료 시험에서 확인. 운영 과금 집계와 임상 정확도는 별도 검증 필요.
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

## GPT-4.1 30,000 TPM 대응 배포

- 배포 객체: deployments/growthai-20260926-staged.zip.
- 배포 SHA256(base64): 9uv6AEGVQyap8UBIRR24R605VmhqWJHcFCaJxidsFuk=.
- 현재 검사 사진 관찰과 참고영상 기반 종합 비교를 분리. 모든 현재 사진은
  첫 호출에서 high detail로 관찰하며 성별에 맞는 전체 연령 참고영상은
  두 번째 호출에 유지한다. 단계 사이 61초 대기.
- 종합 호출은 현재 사진 대신 파일별 관찰 기록을 받는다. 이 제한을 보고서에 표시.
  관찰 ID/부위 누락·중복·불일치는 종합 전에 차단한다.
- 검색 텍스트는 발췌 여부를 표시해 제한하고 필수 단계 정의 원문과 모든 참고영상 유지.
- 요청량 초과 한 건을 같은 크기로 재시도하지 않는다. 일시적 429만 61초 후 한 번 재시도.
  명시적 429/크레딧 거절은 원장에 rejected로 기록하고 해당 예비금을 해제한다.
  시간초과·알 수 없는 실패는 예비금을 유지한다. 과거 미확정 기록은 변경하지 않았다.
- Python 98개, JavaScript 5개 통과. 추가 제한시간 변경 후 관련 테스트 2개 재통과.
- 실제 OpenAI API 가상 시험: 환자자료 없는 가상 이미지 12장 + 참고영상 18장,
  2회 호출, 약 88.82초, 입력 토큰 합계 32,668 / 출력 4,134. 두 요청 모두 성공.
  가상 이미지 12개를 unusable로 분류하고 골연령 추정은 보류함.
  이 로컬 시험 비용은 운영 원장 집계 밖이며 임상 정확도를 검증한 것은 아님.
- Lambda Active / LastUpdateStatus Successful 및 로컬/운영 ZIP 해시 일치 확인.

## MPS 단계·융합 평가·자료실 연결

- 배포 객체: deployments/growthai-20260926-mps-stage.zip.
- SHA256(base64): lRuYs9QmLLHkrwUQ82a8Cdiosce2Mrxjiumg5QDwcfM=.
- Lambda Active / Successful, 배포 해시 일치 확인.
- 사용자 정의 Stage 0–4를 프롬프트·검증·화면에 연결. 세부 근거 부족은 판단 보류.
- 9번은 3개월 추적·단계별 운동과 회복·체성분 및 영양의 세 문단 MPS 관리 제안.
  정상 체지방이나 근육 증가 등 확인되지 않은 판단을 생성하지 않는다.
- references/ 원본 11개 업로드 완료. 서명 다운로드 11개 모두 로컬 SHA256와 일치,
  익명 접근 403 확인. 앱 경로는 권한 확인 후 5분 서명 URL을 발급한다.
- Python 116개 통과. 브라우저 데스크톱·모바일 가로 넘침 없음,
  단계 5개 및 관리 제안 3문단 렌더링 확인, 페이지 오류 없음.
- 변경된 프롬프트 실제 API 가상 시험: 12장+참고영상18장, 2회 호출,
  89.38초, 입력32,934 / 출력3,911. 가상 영상은 판독 불가, 골연령 판단 보류.
  실제 환자·로그인 운영 흐름 또는 임상 정확도를 검증한 시험은 아님.
