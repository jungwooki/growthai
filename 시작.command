#!/bin/zsh
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv || exit 1
  .venv/bin/python -m pip install -r requirements.txt || exit 1
fi
if [[ ! -f .env ]]; then cp .env.example .env; fi
print 'MPS Growth 시작: http://127.0.0.1:8093'
print '이 창을 열어두세요. 종료: Control+C'
(sleep 2; open http://127.0.0.1:8093) &
.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8093
