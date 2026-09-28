"""진입점: OS에 맞는 위젯을 실행한다.

    python -m claude_usage [--interval 초] [--once] [--tray]
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    p = argparse.ArgumentParser(prog="claude_usage", description="Claude 사용량 위젯")
    p.add_argument("--interval", type=float, default=120, help="갱신 주기(초), 기본 120, 최소 30")
    p.add_argument("--once", action="store_true", help="위젯 없이 한 번 조회해서 출력")
    p.add_argument("--tray", action="store_true", help="(Windows) 작업표시줄 위젯 대신 트레이 아이콘으로 표시")
    args = p.parse_args()
    interval = max(30.0, args.interval)

    if args.once:
        from .api import UsageError, fetch_usage

        try:
            u = fetch_usage()
        except UsageError as e:
            sys.exit(f"오류: {e}")
        for name, w in (("5시간", u.five_hour), ("주간", u.seven_day)):
            print(f"{name}: " + (f"{w.percent:.0f}%  {w.reset_text()}" if w else "-"))
        return

    if sys.platform == "darwin":
        from .menubar_mac import main as run
    elif sys.platform == "win32" and not args.tray:
        from .taskbar_win import main as run
    else:
        from .tray import main as run
    run(interval)


if __name__ == "__main__":
    main()
