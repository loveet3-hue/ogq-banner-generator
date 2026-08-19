#!/bin/zsh
# 배포용 zip 생성 (실행 권한 보존) → Drive Ai개발 폴더에 자동 복사
set -e
cd "$(dirname "$0")/.."
SRC="$(pwd)"
NAME="OGQ 배너 생성기"
STAGE="$(mktemp -d)"
rsync -a --exclude output --exclude .cache --exclude build/icon.iconset --exclude .DS_Store --exclude "*.zip" "$SRC/" "$STAGE/$NAME/"
codesign --force --deep --sign - "$SRC/배너 생성기.app" >/dev/null 2>&1
rsync -a "$SRC/배너 생성기.app/" "$STAGE/$NAME/배너 생성기.app/"
chmod +x "$STAGE/$NAME/배너 생성기.app/Contents/MacOS/applet" "$STAGE/$NAME/배너 생성기.command" "$STAGE/$NAME/build/run.sh" "$STAGE/$NAME/앱이 안 열리면 여기 더블클릭.command"
cd "$STAGE"
ditto -c -k --sequesterRsrc --keepParent "$NAME" "$NAME.zip"
cp "$NAME.zip" "$SRC/$NAME.zip"
echo "✓ 생성: $SRC/$NAME.zip"
for d in ~/Library/CloudStorage/GoogleDrive-*/공유\ 드라이브/112_운영팀/08.기타\ 자료/Ai개발; do
  if [ -d "$d" ]; then
    cp "$NAME.zip" "$d/$NAME.zip"
    rsync -a --delete --exclude output --exclude .cache --exclude "*.zip" "$SRC/" "$d/_개발용 소스 (다운로드하지 마세요)/ogq-banner-generator/"
    echo "✓ Drive 복사: $d/$NAME.zip"
  fi
done
rm -rf "$STAGE"
