#!/bin/zsh
# 실행 권한/격리 속성 때문에 앱이 안 열릴 때 복구용
cd "$(dirname "$0")"
chmod +x "배너 생성기.app/Contents/MacOS/applet" "배너 생성기.command" build/run.sh 2>/dev/null
xattr -cr "배너 생성기.app" 2>/dev/null
codesign --force --deep --sign - "배너 생성기.app" >/dev/null 2>&1
echo "복구 완료! 이제 「배너 생성기.app」을 더블클릭하세요."
open .
read "?Enter를 누르면 닫힙니다."
