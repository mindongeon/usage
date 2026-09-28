"""Windows 작업표시줄 위젯.

Windows 11은 작업표시줄에 직접 붙는 deskband를 지원하지 않으므로,
작업표시줄 트레이(시계) 왼쪽 빈 공간에 투명한 always-on-top 창을 겹쳐 띄운다.
(TrafficMonitor 등과 같은 방식)

    5시간 ▓▓▓░░░  20%
    주간  ▓░░░░░   3%

- 좌클릭 드래그: 가로 위치 이동 (저장됨)
- 우클릭: 리셋 시각, 새로고침, 위치 초기화, 자동 실행, 종료
- 전체 화면 앱 실행 중이거나 작업표시줄이 숨겨지면 같이 숨는다.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import winreg
from ctypes import wintypes as w
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

from . import icons
from . import api
from .api import Usage, Window
from .poller import Poller

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

# ---------------------------------------------------------------- Win32 상수

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000

WM_DESTROY = 0x0002
WM_TIMER = 0x0113
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_MOUSEACTIVATE = 0x0021
WM_APP_UPDATE = 0x8000 + 1
MA_NOACTIVATE = 3

SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = w.HWND(-1)
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

ULW_ALPHA = 0x2
AC_SRC_OVER = 0x0
AC_SRC_ALPHA = 0x1

MF_STRING = 0x0
MF_GRAYED = 0x1
MF_CHECKED = 0x8
MF_SEPARATOR = 0x800
MF_POPUP = 0x10
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002
TPM_BOTTOMALIGN = 0x0020

TIMER_POSITION = 1
TIMER_THEME = 2

CMD_REFRESH, CMD_RESET_POS, CMD_AUTOSTART, CMD_QUIT = 1, 2, 3, 9
CMD_SOURCE = {20: "auto", 21: "local", 22: "wsl"}
SOURCE_LABELS = {"auto": "자동 (Windows 우선)", "local": "Windows 로그인", "wsl": "WSL 로그인"}

# ---------------------------------------------------------------- 구조체


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE),
        ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR),
        ("lpszClassName", w.LPCWSTR), ("hIconSm", w.HICON),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG),
        ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
        ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG), ("biYPelsPerMeter", w.LONG),
        ("biClrUsed", w.DWORD), ("biClrImportant", w.DWORD),
    ]


def _sig(fn, restype, *argtypes):
    fn.restype = restype
    fn.argtypes = argtypes


_sig(user32.DefWindowProcW, LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_sig(user32.RegisterClassExW, w.ATOM, ctypes.POINTER(WNDCLASSEXW))
_sig(user32.CreateWindowExW, w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
     ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID)
_sig(user32.FindWindowW, w.HWND, w.LPCWSTR, w.LPCWSTR)
_sig(user32.FindWindowExW, w.HWND, w.HWND, w.HWND, w.LPCWSTR, w.LPCWSTR)
_sig(user32.GetWindowRect, w.BOOL, w.HWND, ctypes.POINTER(w.RECT))
_sig(user32.SetWindowPos, w.BOOL, w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT)
_sig(user32.ShowWindow, w.BOOL, w.HWND, ctypes.c_int)
_sig(user32.SetTimer, ctypes.c_size_t, w.HWND, ctypes.c_size_t, w.UINT, w.LPVOID)
_sig(user32.PostMessageW, w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_sig(user32.GetMessageW, w.BOOL, ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT)
_sig(user32.TranslateMessage, w.BOOL, ctypes.POINTER(w.MSG))
_sig(user32.DispatchMessageW, LRESULT, ctypes.POINTER(w.MSG))
_sig(user32.PostQuitMessage, None, ctypes.c_int)
_sig(user32.DestroyWindow, w.BOOL, w.HWND)
_sig(user32.GetDC, w.HDC, w.HWND)
_sig(user32.ReleaseDC, ctypes.c_int, w.HWND, w.HDC)
_sig(user32.UpdateLayeredWindow, w.BOOL, w.HWND, w.HDC, ctypes.POINTER(w.POINT), ctypes.POINTER(w.SIZE),
     w.HDC, ctypes.POINTER(w.POINT), w.COLORREF, ctypes.POINTER(BLENDFUNCTION), w.DWORD)
_sig(user32.GetCursorPos, w.BOOL, ctypes.POINTER(w.POINT))
_sig(user32.SetCapture, w.HWND, w.HWND)
_sig(user32.ReleaseCapture, w.BOOL)
_sig(user32.GetCapture, w.HWND)
_sig(user32.CreatePopupMenu, w.HMENU)
_sig(user32.AppendMenuW, w.BOOL, w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR)
_sig(user32.TrackPopupMenu, w.BOOL, w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.LPVOID)
_sig(user32.DestroyMenu, w.BOOL, w.HMENU)
_sig(user32.SetForegroundWindow, w.BOOL, w.HWND)
_sig(user32.LoadCursorW, w.HANDLE, w.HINSTANCE, w.LPVOID)
_sig(user32.GetDpiForWindow, w.UINT, w.HWND)
_sig(gdi32.CreateCompatibleDC, w.HDC, w.HDC)
_sig(gdi32.CreateDIBSection, w.HBITMAP, w.HDC, ctypes.POINTER(BITMAPINFOHEADER), w.UINT,
     ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.DWORD)
_sig(gdi32.SelectObject, w.HGDIOBJ, w.HDC, w.HGDIOBJ)
_sig(gdi32.DeleteObject, w.BOOL, w.HGDIOBJ)
_sig(gdi32.DeleteDC, w.BOOL, w.HDC)
_sig(kernel32.GetModuleHandleW, w.HMODULE, w.LPCWSTR)
_sig(kernel32.CreateMutexW, w.HANDLE, w.LPVOID, w.BOOL, w.LPCWSTR)
_sig(shell32.SHQueryUserNotificationState, ctypes.c_long, ctypes.POINTER(ctypes.c_int))

# ---------------------------------------------------------------- 설정

CONFIG_PATH = Path(os.environ.get("APPDATA", Path.home())) / "ClaudeUsage" / "config.json"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ClaudeUsage"


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(cfg), encoding="utf-8")
    except OSError:
        pass


def _is_light_theme() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False


def _autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    script = Path(__file__).resolve().parent.parent / "run_widget.pyw"
    return f'"{exe}" "{script}"'


def _autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except OSError:
        return False


def _set_autostart(enable: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enable:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except OSError:
                pass


# ---------------------------------------------------------------- 렌더링

ROWS = (("five_hour", "5시간"), ("seven_day", "주간"))


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("malgunbd.ttf", "malgun.ttf", "segoeuib.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def render_widget(usage: Usage | None, error: str | None, height: int, scale: float, light: bool) -> Image.Image:
    """작업표시줄 높이에 맞춰 두 줄짜리 위젯 이미지를 만든다 (RGBA, 투명 배경)."""
    s = scale
    label_w, bar_w, pct_w, gap = round(34 * s), round(46 * s), round(36 * s), round(6 * s)
    width = label_w + gap + bar_w + gap + pct_w
    img = Image.new("RGBA", (width, height), (0, 0, 0, 1))  # alpha 1: 투명하지만 클릭은 받음

    fg = (0, 0, 0, 255) if light else (255, 255, 255, 255)
    track = (0, 0, 0, 55) if light else (255, 255, 255, 60)
    font = _font(round(12 * s))
    row_h = round(18 * s)
    top = (height - row_h * 2) // 2

    text_mask = Image.new("L", img.size, 0)
    tdraw = ImageDraw.Draw(text_mask)
    shapes = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shapes)

    for i, (key, label) in enumerate(ROWS):
        cy = top + row_h * i + row_h // 2
        win: Window | None = getattr(usage, key) if usage else None
        tdraw.text((label_w, cy), label, font=font, fill=255, anchor="rm")

        bx = label_w + gap
        bh = max(4, round(6 * s))
        by = cy - bh // 2
        sdraw.rounded_rectangle((bx, by, bx + bar_w, by + bh), radius=bh // 2, fill=track)
        if win is not None and win.percent > 0:
            fill_w = max(bh, round(bar_w * min(win.percent, 100) / 100))
            sdraw.rounded_rectangle((bx, by, bx + fill_w, by + bh), radius=bh // 2,
                                    fill=icons.color_for(win.percent) + (255,))

        if win is not None:
            pct = f"{win.percent:.0f}%"
        else:
            pct = "!" if error else "…"
        tdraw.text((width, cy), pct, font=font, fill=255, anchor="rm")

    img.alpha_composite(shapes)
    text_layer = Image.new("RGBA", img.size, fg)
    text_layer.putalpha(text_mask)
    img.alpha_composite(text_layer)
    return img


def _premultiplied_bgra(img: Image.Image) -> bytes:
    r, g, b, a = img.split()
    mul = ImageChops.multiply
    return Image.merge("RGBA", (mul(r, a), mul(g, a), mul(b, a), a)).tobytes("raw", "BGRA")


# ---------------------------------------------------------------- 위젯 창


class TaskbarWidget:
    def __init__(self, interval: float):
        self.cfg = _load_config()
        api.set_source(self.cfg.get("source", "auto"))
        self.emails: dict[str, str | None] = {}
        self.usage: Usage | None = None
        self.error: str | None = None
        self.light = _is_light_theme()
        self.hwnd = None
        self.size = (0, 0)
        self.pos = (0, 0)
        self.scale = 1.0
        self.visible = False
        self.drag: tuple[int, float] | None = None  # (시작 커서 x, 시작 offset)
        self._pending: tuple[Usage | None, str | None] | None = None
        self._wndproc = WNDPROC(self._proc)  # GC 방지용 참조 유지
        self.poller = Poller(interval, self._on_poll)

    # ---- 창 생성 / 루프

    def run(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))  # IDC_ARROW
        wc.lpszClassName = "ClaudeUsageTaskbarWidget"
        user32.RegisterClassExW(ctypes.byref(wc))

        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE,
            wc.lpszClassName, "Claude Usage", WS_POPUP,
            0, 0, 1, 1, None, None, hinst, None,
        )
        self._redraw()
        user32.SetTimer(self.hwnd, TIMER_POSITION, 300, None)
        user32.SetTimer(self.hwnd, TIMER_THEME, 5000, None)
        self.poller.start()
        threading.Thread(target=self._load_emails, daemon=True).start()

        msg = w.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        self.poller.stop()

    def _load_emails(self) -> None:
        for src in ("local", "wsl"):
            self.emails[src] = api.fetch_email(src)

    def _on_poll(self, usage: Usage | None, error: str | None) -> None:
        # 폴러 스레드 → UI 스레드로 전달
        self._pending = (usage, error)
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_APP_UPDATE, 0, 0)

    # ---- 위치 계산

    def _taskbar(self) -> tuple[w.RECT, w.RECT | None] | None:
        tb = user32.FindWindowW("Shell_TrayWnd", None)
        if not tb:
            return None
        tb_rect = w.RECT()
        user32.GetWindowRect(tb, ctypes.byref(tb_rect))
        dpi = user32.GetDpiForWindow(tb) or 96
        self.scale = dpi / 96
        tray = user32.FindWindowExW(tb, None, "TrayNotifyWnd", None)
        tray_rect = None
        if tray:
            r = w.RECT()
            user32.GetWindowRect(tray, ctypes.byref(r))
            if r.right - r.left > 0 and tb_rect.left <= r.left <= tb_rect.right:
                tray_rect = r
        return tb_rect, tray_rect

    def _should_hide(self, tb: w.RECT) -> bool:
        state = ctypes.c_int(0)
        if shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0 and state.value in (2, 3, 4):
            return True  # 전체 화면 앱 / 프레젠테이션 모드
        screen_h = user32.GetSystemMetrics(1)
        return tb.bottom - tb.top < 8 or tb.top >= screen_h - 4  # 자동 숨김 상태

    def _target(self) -> tuple[int, int, int] | None:
        """(x, y, height) 또는 None(숨김)."""
        found = self._taskbar()
        if not found:
            return None
        tb, tray = found
        if self._should_hide(tb):
            return None
        height = tb.bottom - tb.top
        anchor = (tray.left if tray else tb.right - round(300 * self.scale)) - round(8 * self.scale)
        x = anchor - self.size[0] - round(self.cfg.get("offset", 0) * self.scale)
        x = max(tb.left, min(x, tb.right - self.size[0]))
        return x, tb.top, height

    # ---- 그리기

    def _redraw(self) -> None:
        found = self._taskbar()
        height = (found[0].bottom - found[0].top) if found else round(48 * self.scale)
        img = render_widget(self.usage, self.error, height, self.scale, self.light)
        self.size = img.size
        target = self._target()
        if target:
            self.pos = (target[0], target[1])
        self._update_layered(img)
        self._sync_visibility(target)

    def _update_layered(self, img: Image.Image) -> None:
        wdt, hgt = img.size
        data = _premultiplied_bgra(img)
        screen = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(screen)
        bmi = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=wdt, biHeight=-hgt,
                               biPlanes=1, biBitCount=32, biCompression=0)
        bits = ctypes.c_void_p()
        bmp = gdi32.CreateDIBSection(screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        ctypes.memmove(bits, data, len(data))
        old = gdi32.SelectObject(mem, bmp)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(
            self.hwnd, screen, ctypes.byref(w.POINT(*self.pos)), ctypes.byref(w.SIZE(wdt, hgt)),
            mem, ctypes.byref(w.POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA,
        )
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)

    def _sync_visibility(self, target) -> None:
        if target is None:
            if self.visible:
                user32.ShowWindow(self.hwnd, SW_HIDE)
                self.visible = False
            return
        x, y, height = target
        if height != self.size[1]:
            self._redraw()
            return
        self.pos = (x, y)
        # 작업표시줄을 클릭하면 작업표시줄이 위로 올라오므로 주기적으로 맨 앞으로 다시 올린다
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
        if not self.visible:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.visible = True

    # ---- 메뉴

    def _menu(self) -> None:
        menu = user32.CreatePopupMenu()
        for key, label in ROWS:
            win: Window | None = getattr(self.usage, key) if self.usage else None
            text = f"{label}: {win.percent:.0f}%  ·  {win.reset_text()}" if win else f"{label}: -"
            user32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, text)
        if self.error:
            user32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, f"⚠ {self.error}")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, CMD_REFRESH, "지금 새로고침")
        sub = user32.CreatePopupMenu()
        for cmd_id, src in CMD_SOURCE.items():
            label = SOURCE_LABELS[src]
            if self.emails.get(src):
                label += f"  —  {self.emails[src]}"
            elif src != "auto" and src in self.emails:
                label += "  —  (없음)"
            flags = MF_STRING | (MF_CHECKED if api.get_source() == src else 0)
            user32.AppendMenuW(sub, flags, cmd_id, label)
        user32.AppendMenuW(menu, MF_POPUP, sub, "계정")
        user32.AppendMenuW(menu, MF_STRING, CMD_RESET_POS, "위치 초기화")
        auto = _autostart_enabled()
        user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if auto else 0), CMD_AUTOSTART, "Windows 시작 시 자동 실행")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, CMD_QUIT, "종료")

        pt = w.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_BOTTOMALIGN,
                                    pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(menu)

        if cmd in CMD_SOURCE:
            api.set_source(CMD_SOURCE[cmd])
            self.cfg["source"] = CMD_SOURCE[cmd]
            _save_config(self.cfg)
            self.poller.refresh_now()
        elif cmd == CMD_REFRESH:
            self.poller.refresh_now()
        elif cmd == CMD_RESET_POS:
            self.cfg["offset"] = 0
            _save_config(self.cfg)
            self._sync_visibility(self._target())
        elif cmd == CMD_AUTOSTART:
            try:
                _set_autostart(not auto)
            except OSError:
                pass
        elif cmd == CMD_QUIT:
            user32.DestroyWindow(self.hwnd)

    # ---- 메시지 처리

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_APP_UPDATE and self._pending:
            self.usage, self.error = self._pending
            if self.usage is not None:
                self.error = None
            self._redraw()
            return 0
        if msg == WM_TIMER:
            if wparam == TIMER_THEME:
                light = _is_light_theme()
                if light != self.light:
                    self.light = light
                    self._redraw()
            elif not self.drag:
                self._sync_visibility(self._target())
            return 0
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if msg == WM_LBUTTONDOWN:
            pt = w.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            self.drag = (pt.x, float(self.cfg.get("offset", 0)))
            user32.SetCapture(hwnd)
            return 0
        if msg == WM_MOUSEMOVE and self.drag and user32.GetCapture() == hwnd:
            pt = w.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            start_x, start_off = self.drag
            self.cfg["offset"] = start_off - (pt.x - start_x) / self.scale
            target = self._target()
            if target:
                self.pos = (target[0], target[1])
                user32.SetWindowPos(hwnd, HWND_TOPMOST, target[0], target[1], 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
            return 0
        if msg == WM_LBUTTONUP and self.drag:
            user32.ReleaseCapture()
            self.drag = None
            _save_config(self.cfg)
            return 0
        if msg == WM_RBUTTONUP:
            self._menu()
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def main(interval: float) -> None:
    # 중복 실행 방지 (자동 실행 + 수동 실행 등)
    kernel32.CreateMutexW(None, False, "Local\\ClaudeUsageTaskbarWidget")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        pass
    TaskbarWidget(interval).run()
