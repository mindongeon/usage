"""백그라운드에서 주기적으로 사용량을 가져와 콜백으로 넘긴다."""

from __future__ import annotations

import threading
from typing import Callable

from .api import Usage, UsageError, fetch_usage


class Poller:
    def __init__(self, interval: float, on_update: Callable[[Usage | None, str | None], None]):
        self.interval = interval
        self.on_update = on_update
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def refresh_now(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.on_update(fetch_usage(), None)
            except UsageError as e:
                self.on_update(None, str(e))
            except Exception as e:  # 위젯이 죽지 않도록 모든 예외를 표시로 돌린다
                self.on_update(None, f"알 수 없는 오류: {e}")
            self._wake.wait(self.interval)
            self._wake.clear()
