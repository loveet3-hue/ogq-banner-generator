#!/bin/bash
# OGQ 크리에이터 인터뷰 카드뉴스 생성기 - 맥용
cd "$(dirname "$0")"
echo "============================================"
echo " OGQ 크리에이터 인터뷰 카드뉴스 생성기"
echo "============================================"
echo ""
echo "[1/3] 설문 응답 엑셀 파일을 이 창에 드래그한 뒤 Enter:"
read EXCEL
# 드래그 시 붙는 따옴표/이스케이프 공백 정리
EXCEL="${EXCEL//\\ / }"
EXCEL="$(echo "$EXCEL" | sed "s/^[ '\"]*//; s/[ '\"]*$//")"
echo ""
echo "[2/3] 응답자 선택 - 그냥 Enter=전체 일괄생성 / 숫자 입력=해당 응답자만 (0부터):"
read WHO
echo ""
echo "[3/3] 배경 테마 (auto/mint/pink/lavender/sky/cream/peach/random, Enter=auto):"
read THEME
echo ""

ARGS=(--excel "$EXCEL" --preview)
if [ -z "$WHO" ]; then ARGS+=(--all); else ARGS+=(--row "$WHO"); fi
if [ -n "$THEME" ]; then ARGS+=(--theme "$THEME"); fi

python3 make_cards.py "${ARGS[@]}"

echo ""
echo "============================================"
echo " 끝! output 폴더에서 결과를 확인하세요."
echo "============================================"
read -p "Enter를 누르면 닫힙니다..."
