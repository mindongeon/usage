"""Claude 구독 사용량 조회.

Claude Code가 `/usage`에서 쓰는 OAuth 사용량 엔드포인트를 호출한다.
토큰은 Claude Code가 저장해 둔 자격 증명을 읽기만 하며, 갱신(refresh)은 하지 않는다.
(갱신하면 refresh token이 회전되어 Claude Code 쪽 로그인이 깨질 수 있음.
 토큰이 만료되면 Claude Code를 한 번 실행하면 자동 갱신된다.)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN_SERVICE = "Claude Code-credentials"


class UsageError(Exception):
    """사용자에게 보여줄 수 있는 짧은 오류 메시지."""


@dataclass
class Window:
    percent: float
    resets_at: datetime | None

    def reset_text(self) -> str:
        if not self.resets_at:
            return "-"
        local = self.resets_at.astimezone()
        delta = local - datetime.now().astimezone()
        mins = max(0, int(delta.total_seconds() // 60))
        if mins >= 24 * 60:
            left = f"{mins // (24 * 60)}일 {mins % (24 * 60) // 60}시간"
        elif mins >= 60:
            left = f"{mins // 60}시간 {mins % 60}분"
        else:
            left = f"{mins}분"
        return f"{local:%m/%d %H:%M} 리셋 ({left} 남음)"


@dataclass
class Usage:
    five_hour: Window | None
    seven_day: Window | None


# ---------------------------------------------------------------- credentials

def _credentials_json() -> str:
    """자격 증명 JSON 문자열을 찾는다.

    우선순위:
      1. CLAUDE_CREDENTIALS_PATH 환경변수
      2. macOS 키체인 ("Claude Code-credentials")
      3. $CLAUDE_CONFIG_DIR/.credentials.json 또는 ~/.claude/.credentials.json
      4. (Windows) WSL 안의 ~/.claude/.credentials.json — Claude Code를 WSL에서 쓰는 경우
    """
    override = os.environ.get("CLAUDE_CREDENTIALS_PATH")
    if override:
        return Path(override).expanduser().read_text(encoding="utf-8")

    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass

    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    path = config_dir / ".credentials.json"
    if path.exists():
        return path.read_text(encoding="utf-8")

    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["wsl.exe", "-e", "sh", "-c", "cat ~/.claude/.credentials.json"],
                capture_output=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.decode("utf-8")
        except (OSError, subprocess.TimeoutExpired):
            pass

    raise UsageError("Claude Code 로그인 정보를 찾을 수 없습니다")


def load_token() -> str:
    try:
        data = json.loads(_credentials_json())
        return data["claudeAiOauth"]["accessToken"]
    except (ValueError, KeyError, TypeError) as e:
        raise UsageError("자격 증명 형식을 읽을 수 없습니다") from e


# ---------------------------------------------------------------- fetch

def _parse_window(raw) -> Window | None:
    if not isinstance(raw, dict) or raw.get("utilization") is None:
        return None
    resets = raw.get("resets_at")
    return Window(
        percent=float(raw["utilization"]),
        resets_at=datetime.fromisoformat(resets) if resets else None,
    )


def fetch_usage(timeout: float = 15) -> Usage:
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {load_token()}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
            "User-Agent": "claude-usage-widget/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise UsageError("토큰 만료 — Claude Code를 한 번 실행하세요") from e
        if e.code == 429:
            raise UsageError("요청이 너무 많습니다 (잠시 후 재시도)") from e
        raise UsageError(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UsageError("네트워크 오류") from e

    return Usage(
        five_hour=_parse_window(data.get("five_hour")),
        seven_day=_parse_window(data.get("seven_day")),
    )


if __name__ == "__main__":
    u = fetch_usage()
    for name, w in (("5시간", u.five_hour), ("주간", u.seven_day)):
        print(f"{name}: " + (f"{w.percent:.0f}%  {w.reset_text()}" if w else "-"))
