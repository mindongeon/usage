"""앱 아이콘(.ico / .icns / .png)을 생성한다. 빌드 스크립트가 호출한다."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_usage.icons import _font  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "build_assets"


def app_icon(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size // 16
    d.rounded_rectangle((pad, pad, size - pad, size - pad), radius=size // 5, fill=(217, 119, 87))
    # 두 개의 게이지 막대 (5시간 / 주간)
    bar_h = size // 9
    left, right = size // 5, size - size // 5
    for i, frac in enumerate((0.65, 0.35)):
        top = size // 2 - bar_h - size // 20 + i * (bar_h + size // 10) + size // 20
        d.rounded_rectangle((left, top, right, top + bar_h), radius=bar_h // 2, fill=(176, 84, 56))
        d.rounded_rectangle((left, top, left + int((right - left) * frac), top + bar_h),
                            radius=bar_h // 2, fill="white")
    font = _font(size // 6)
    d.text((size // 2, size // 4), "%", font=font, fill="white", anchor="mm")
    return img


def main() -> None:
    OUT.mkdir(exist_ok=True)
    icon = app_icon()
    icon.save(OUT / "app.png")
    icon.save(OUT / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    if sys.platform == "darwin":
        icon.save(OUT / "app.icns")
    print(f"icons -> {OUT}")


if __name__ == "__main__":
    main()
