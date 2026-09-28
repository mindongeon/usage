#!/usr/bin/env bash
# macOS용 ClaudeUsage.app + ClaudeUsage.dmg 빌드 -> dist/
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv-build
source .venv-build/bin/activate
python -m pip install -q --upgrade pip
pip install -q -r requirements-build.txt

python packaging/make_icons.py
pyinstaller --noconfirm --clean packaging/claude_usage.spec

# 서명 인증서가 없으면 ad-hoc 서명 (Apple Silicon에서 실행에 필요)
codesign --force --deep --sign - dist/ClaudeUsage.app

# DMG: 앱 + Applications 바로가기
STAGE=dist/dmg
rm -rf "$STAGE" dist/ClaudeUsage.dmg
mkdir -p "$STAGE"
cp -R dist/ClaudeUsage.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Claude Usage" -srcfolder "$STAGE" -ov -format UDZO dist/ClaudeUsage.dmg
rm -rf "$STAGE"

echo "완료: dist/ClaudeUsage.dmg"
