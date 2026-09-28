# PyInstaller 스펙: Windows는 단일 ClaudeUsage.exe, macOS는 ClaudeUsage.app 번들을 만든다.
# 사용: pyinstaller --noconfirm packaging/claude_usage.spec   (프로젝트 루트에서)
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
ASSETS = Path(SPECPATH) / "build_assets"
NAME = "ClaudeUsage"
IS_MAC = sys.platform == "darwin"

hidden = ["claude_usage.menubar_mac"] if IS_MAC else ["claude_usage.taskbar_win", "claude_usage.tray", "pystray._win32"]

a = Analysis(
    [str(ROOT / "run_widget.pyw")],
    pathex=[str(ROOT)],
    hiddenimports=hidden,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)

if IS_MAC:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False)
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME)
    app = BUNDLE(
        coll,
        name=f"{NAME}.app",
        icon=str(ASSETS / "app.icns"),
        bundle_identifier="com.local.claudeusage",
        info_plist={
            "LSUIElement": True,  # Dock 아이콘 없이 메뉴바 전용
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
        },
    )
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas,
        name=NAME,
        console=False,
        icon=str(ASSETS / "app.ico"),
        upx=False,
    )
