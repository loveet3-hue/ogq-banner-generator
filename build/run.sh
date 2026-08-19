#!/bin/zsh
# 배너 생성기 실제 실행 스크립트 (런처 앱 / .command 에서 호출)
cd "$(dirname "$0")/.."

# python3 확인
if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "이 Mac에 Python3 가 없습니다."
  echo "잠시 후 뜨는 창에서 [설치]를 눌러 '명령어 라인 도구'를 설치한 뒤"
  echo "설치가 끝나면 배너 생성기를 다시 실행해 주세요. (5~10분 소요)"
  echo ""
  xcode-select --install 2>/dev/null
  read "?Enter를 누르면 창이 닫힙니다."
  exit 1
fi

PY="$(command -v python3)"

# 필요한 패키지 자동 설치
if ! "$PY" -c "import PIL, requests" 2>/dev/null; then
  echo ""
  echo "첫 실행 준비 중... (필요한 구성요소 설치, 1~2분 걸릴 수 있어요)"
  "$PY" -m pip install --user --quiet pillow requests 2>/dev/null \
    || "$PY" -m pip install --user --quiet --break-system-packages pillow requests 2>/dev/null \
    || "$PY" -m pip install --quiet pillow requests 2>/dev/null \
    || "$PY" -m pip install --quiet --break-system-packages pillow requests
  if ! "$PY" -c "import PIL, requests" 2>/dev/null; then
    echo ""
    echo "구성요소 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행해 주세요."
    read "?Enter를 누르면 창이 닫힙니다."
    exit 1
  fi
  echo "준비 완료!"
  echo ""
fi

"$PY" banner_gen.py
