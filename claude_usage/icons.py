"""트레이 아이콘 이미지 생성 (Pillow).

작업표시줄 트레이 아이콘은 16~32px로 축소되므로 숫자만 크게 그린다.
두 아이콘은 모양으로 구분한다: 5시간 = 원, 주간 = 둥근 사각형.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

SIZE = 64

GREEN = (46, 160, 67)
AMBER = (212, 140, 0)
RED = (207, 34, 46)
GRAY = (110, 118, 129)

_FONT_CANDIDATES = [
    "segoeuib.ttf",  # Windows
    "arialbd.ttf",  # Windows
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
    "DejaVuSans-Bold.ttf",  # Linux
]


def color_for(percent: float | None) -> tuple[int, int, int]:
    if percent is None:
        return GRAY
    if percent >= 80:
        return RED
    if percent >= 50:
        return AMBER
    return GREEN


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_w: int, max_h: int):
    size = max_h
    while size > 8:
        font = _font(size)
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        if r - l <= max_w and b - t <= max_h:
            return font
        size -= 2
    return _font(size)


def render(percent: float | None, shape: str) -> Image.Image:
    """percent가 None이면 오류 상태('!')를 그린다. shape은 'circle' 또는 'square'."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    box = (0, 0, SIZE - 1, SIZE - 1)
    fill = color_for(percent)
    if shape == "circle":
        draw.ellipse(box, fill=fill)
    else:
        draw.rounded_rectangle(box, radius=12, fill=fill)

    if percent is None:
        text = "!"
    elif percent >= 100:
        text = "MAX"
    else:
        text = str(int(round(percent)))

    inner = 54 if shape == "square" else 48
    font = _fit_font(draw, text, inner, 44)
    draw.text((SIZE / 2, SIZE / 2), text, font=font, fill="white", anchor="mm")
    return img
