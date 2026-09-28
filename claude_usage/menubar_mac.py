"""macOS 상단 메뉴바 위젯: '5h 19% · 7d 3%' 형태로 표시."""

from __future__ import annotations

import rumps

from .api import Usage
from .poller import Poller


def _hide_dock_icon() -> None:
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass


class MenuBarApp(rumps.App):
    def __init__(self, interval: float):
        super().__init__("Claude Usage", title="5h … · 7d …", quit_button="종료")
        self.five_item = rumps.MenuItem("5시간: 불러오는 중…")
        self.week_item = rumps.MenuItem("주간: 불러오는 중…")
        self.status_item = rumps.MenuItem("")
        self.menu = [
            self.five_item,
            self.week_item,
            None,
            rumps.MenuItem("지금 새로고침", callback=lambda _: self.poller.refresh_now()),
            self.status_item,
        ]
        self._latest: tuple[Usage | None, str | None] | None = None
        self.poller = Poller(interval, self._on_update)
        # UI 갱신은 메인 스레드에서: 폴러 결과를 1초 타이머로 반영
        self._timer = rumps.Timer(self._apply, 1)
        self._timer.start()
        self.poller.start()

    def _on_update(self, usage: Usage | None, error: str | None) -> None:
        self._latest = (usage, error)

    def _apply(self, _timer) -> None:
        if self._latest is None:
            return
        usage, error = self._latest
        self._latest = None

        if usage is None:
            self.title = "5h ! · 7d !"
            self.status_item.title = f"⚠ {error}"
            return

        def pct(w):
            return f"{w.percent:.0f}%" if w else "-"

        self.title = f"5h {pct(usage.five_hour)} · 7d {pct(usage.seven_day)}"
        self.five_item.title = (
            f"5시간: {pct(usage.five_hour)} — {usage.five_hour.reset_text()}" if usage.five_hour else "5시간: -"
        )
        self.week_item.title = (
            f"주간: {pct(usage.seven_day)} — {usage.seven_day.reset_text()}" if usage.seven_day else "주간: -"
        )
        self.status_item.title = ""


def main(interval: float) -> None:
    _hide_dock_icon()
    MenuBarApp(interval).run()
