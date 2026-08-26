#!/bin/zsh
# 웹 버전을 내 컴퓨터에서 실행 (브라우저가 자동으로 열립니다)
cd "$(dirname "$0")"
PY="$(command -v python3)"

# 필요한 라이브러리가 없으면 깔아 준다. requirements.txt를 기준으로 하므로
# 나중에 뭘 추가해도 이 파일은 그대로 두면 된다.
NEED=0
for mod in streamlit PIL requests pandas openpyxl pptx; do
  "$PY" -c "import $mod" 2>/dev/null || NEED=1
done
if [ "$NEED" = "1" ]; then
  echo "필요한 프로그램을 설치하는 중입니다. 처음 한 번만 걸립니다 (1~2분)..."
  "$PY" -m pip install --user --quiet -r requirements.txt 2>/dev/null \
    || "$PY" -m pip install --quiet --break-system-packages -r requirements.txt
fi

"$PY" -m streamlit run web_app.py
