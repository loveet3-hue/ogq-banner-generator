#!/bin/bash
# OGQ 카드뉴스 생성기 - 맥용 최초 1회 설치
cd "$(dirname "$0")"

# 맥 보안 차단(quarantine) 해제 + 실행 권한 부여 (같은 폴더의 모든 .command)
xattr -dr com.apple.quarantine . 2>/dev/null
chmod +x ./*.command 2>/dev/null

echo "============================================"
echo " OGQ 카드뉴스 생성기 - 최초 1회 설치 (Mac)"
echo "============================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[오류] 파이썬이 설치되어 있지 않습니다."
    echo "https://www.python.org/downloads/ 에서 파이썬을 먼저 설치해주세요."
    read -p "Enter를 누르면 닫힙니다..."
    exit 1
fi

echo "필요한 프로그램을 설치하는 중... (몇 분 걸릴 수 있어요)"
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
echo ""
echo "============================================"
echo " 설치 완료! 이제 '2_카드뉴스만들기_맥용.command'를 실행하세요."
echo "============================================"
read -p "Enter를 누르면 닫힙니다..."
