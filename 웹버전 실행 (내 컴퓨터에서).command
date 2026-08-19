#!/bin/zsh
# 웹 버전을 내 컴퓨터에서 실행 (브라우저가 자동으로 열립니다)
cd "$(dirname "$0")"
PY="$(command -v python3)"
"$PY" -c "import streamlit" 2>/dev/null || "$PY" -m pip install --user --quiet streamlit pillow requests 2>/dev/null || "$PY" -m pip install --quiet --break-system-packages streamlit pillow requests
"$PY" -m streamlit run web_app.py
