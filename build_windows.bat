@echo off
REM Build ClaudeUsage.exe for Windows -> dist\ClaudeUsage.exe
setlocal
cd /d "%~dp0"

python -m venv .venv-build || goto :error
call .venv-build\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements-build.txt || goto :error

python packaging\make_icons.py || goto :error
pyinstaller --noconfirm --clean packaging\claude_usage.spec || goto :error

echo.
echo Done: dist\ClaudeUsage.exe
exit /b 0

:error
echo Build failed
exit /b 1
