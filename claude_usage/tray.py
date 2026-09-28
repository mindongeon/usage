"""Windows(및 Linux) 작업표시줄 트레이 위젯.

아이콘 두 개(5시간 / 주간)를 트레이에 띄우고 숫자로 사용률(%)을 보여준다.
마우스를 올리면 리셋 시각이, 우클릭하면 메뉴가 나온다.
"""

from __future__ import annotations

import threading

import pystray

from . import icons
from .api import Usage, Window
from .poller import Poller

LABELS = {"five_hour": "5시간", "seven_day": "주간"}
SHAPES = {"five_hour": "circle", "seven_day": "square"}


class TrayApp:
    def __init__(self, interval: float):
        self.icons: dict[str, pystray.Icon] = {}
        self.ready = {k: threading.Event() for k in LABELS}
        self.poller = Poller(interval, self.update)

    def _menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("지금 새로고침", lambda: self.poller.refresh_now(), default=True),
            pystray.MenuItem("종료", self.quit),
        )

    def _run_icon(self, key: str) -> None:
        # Windows에서는 아이콘 창을 만든 스레드에서 메시지 루프를 돌려야 하므로
        # 아이콘 생성과 run()을 같은 스레드에서 한다.
        icon = pystray.Icon(
            f"claude-usage-{key}",
            icons.render(None, SHAPES[key]),
            f"Claude {LABELS[key]} 사용량: 불러오는 중…",
            menu=self._menu(),
        )
        self.icons[key] = icon

        def setup(ic: pystray.Icon) -> None:
            ic.visible = True
            self.ready[key].set()

        icon.run(setup=setup)

    def update(self, usage: Usage | None, error: str | None) -> None:
        for key, label in LABELS.items():
            if not self.ready[key].wait(timeout=10):
                continue
            icon = self.icons[key]
            win: Window | None = getattr(usage, key) if usage else None
            if win is None:
                icon.icon = icons.render(None, SHAPES[key])
                icon.title = f"Claude {label}: {error or '데이터 없음'}"
            else:
                icon.icon = icons.render(win.percent, SHAPES[key])
                # Windows 툴팁은 127자 제한
                icon.title = f"Claude {label} 사용량 {win.percent:.0f}%\n{win.reset_text()}"[:127]

    def quit(self) -> None:
        self.poller.stop()
        for icon in self.icons.values():
            icon.stop()

    def run(self) -> None:
        # 주간 아이콘을 먼저 등록해야 트레이에서 [5시간][주간] 순서로 보이는 경우가 많다
        # (Windows는 새 아이콘을 왼쪽에 추가한다).
        t = threading.Thread(target=self._run_icon, args=("seven_day",), daemon=True)
        t.start()
        self.ready["seven_day"].wait(timeout=10)
        self.poller.start()
        self._run_icon("five_hour")  # 메인 스레드에서 블록
        t.join(timeout=2)


def main(interval: float) -> None:
    TrayApp(interval).run()
