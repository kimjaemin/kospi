#!/bin/bash
# macOS: 더블클릭으로 실행. 처음 한 번은 필요한 패키지를 설치합니다.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
.venv/bin/streamlit run app.py
