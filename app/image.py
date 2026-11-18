"""PNG rendering of a meal plan, for sharing (download, messaging apps, link previews).

Styled like the web "menu": serif dish names, day column on the left, soft type tags.
"""

import os
from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.dates import fmt_week, fmt_weekday
from app.models import MEAL_TYPE_LABELS, MealPlan

WIDTH = 1200
PAD = 80
PAPER = (243, 235, 221)
CARD = (255, 251, 244)
LINE = (231, 220, 203)
INK = (58, 46, 37)
INK_2 = (102, 87, 74)
MUTED = (150, 135, 122)
ACCENT = (201, 100, 63)
TYPE_COLORS = {  # (text/dot, soft background)
    "meat": ((180, 82, 58), (245, 223, 212)),
    "fish": ((63, 117, 144), (223, 233, 236)),
    "vegetarian": ((99, 127, 60), (230, 234, 210)),
}

HEADER_H = 300
DISH_H = 64
ROW_PAD = 30
CARD_PAD_Y = 20
FOOTER_H = 110
DATE_COL = 150

_FONT_FILES = {
    "serif": "Fraunces-Regular.ttf",
    "serif-bold": "Fraunces-SemiBold.ttf",
    "sans": "Inter-Regular.ttf",
    "sans-medium": "Inter-Medium.ttf",
    "sans-bold": "Inter-SemiBold.ttf",
}


@lru_cache(maxsize=32)
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(os.path.join(settings.font_dir, _FONT_FILES[name]), size)
    except OSError:
        return ImageFont.load_default(size=size)


def _fit(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _spaced(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, tracking: float, anchor_center=False) -> None:
    """Draw uppercase text with letter-spacing (Pillow has no native tracking)."""
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x, y = xy
    if anchor_center:
        x -= total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += w + tracking


def render_plan_image(plan: MealPlan) -> bytes:
    days = plan.entries_by_day()
    row_heights = [max(1, len(entries)) * DISH_H + 2 * ROW_PAD for _, entries in days]
    card_h = sum(row_heights) + 2 * CARD_PAD_Y
    height = HEADER_H + card_h + FOOTER_H

    image = Image.new("RGB", (WIDTH, height), PAPER)
    draw = ImageDraw.Draw(image)

    # Header
    center = WIDTH / 2
    _spaced(draw, (center, 104), "DINNER MENU", _font("sans-bold", 20), ACCENT, 5, anchor_center=True)
    draw.line((center - 150, 96, center - 110, 96), fill=(217, 202, 179), width=2)
    draw.line((center + 110, 96, center + 150, 96), fill=(217, 202, 179), width=2)
    title_font = _font("serif-bold", 76)
    draw.text((center, 186), _fit(draw, plan.name, title_font, WIDTH - 2 * PAD), font=title_font, fill=INK, anchor="ms")
    draw.text((center, 238), fmt_week(plan.week_start), font=_font("sans", 28), fill=MUTED, anchor="ms")

    # Menu card
    top = HEADER_H
    draw.rounded_rectangle((PAD - 30, top, WIDTH - PAD + 30, top + card_h), radius=28, fill=CARD, outline=LINE, width=2)
    y = top + CARD_PAD_Y
    dish_font, tag_font = _font("serif", 38), _font("sans-bold", 17)
    for index, ((day, entries), row_h) in enumerate(zip(days, row_heights)):
        if index:
            draw.line((PAD, y, WIDTH - PAD, y), fill=LINE, width=2)
        # Date column
        _spaced(draw, (PAD + 4, y + ROW_PAD + 22), fmt_weekday(day)[:3].upper(), _font("sans-bold", 17), MUTED, 3)
        draw.text((PAD, y + ROW_PAD + 70), str(day.day), font=_font("serif-bold", 50), fill=INK, anchor="ls")

        # Dishes
        dish_y = y + ROW_PAD + DISH_H / 2
        text_left = PAD + DATE_COL
        right = WIDTH - PAD
        for entry in entries or [None]:
            name = entry.display_name if entry else None
            meal_type = entry.display_type if entry else None
            name_max = right - text_left
            if meal_type in TYPE_COLORS:
                fg, bg = TYPE_COLORS[meal_type]
                label = MEAL_TYPE_LABELS[meal_type].upper()
                label_w = sum(draw.textlength(ch, font=tag_font) for ch in label) + 1.5 * (len(label) - 1)
                tag_w = label_w + 50
                draw.rounded_rectangle((right - tag_w, dish_y - 19, right, dish_y + 19), radius=19, fill=bg)
                draw.ellipse((right - tag_w + 17, dish_y - 4, right - tag_w + 25, dish_y + 4), fill=fg)
                _spaced(draw, (right - tag_w + 34, dish_y + 6), label, tag_font, fg, 1.5)
                name_max = right - tag_w - 28 - text_left
            draw.text(
                (text_left, dish_y),
                _fit(draw, name or ("Nothing planned" if entry and entry.skipped else "To be decided"), dish_font, name_max),
                font=dish_font,
                fill=INK if name else MUTED,
                anchor="lm",
            )
            dish_y += DISH_H
        y += row_h

    # Footer
    footer_y = height - FOOTER_H / 2 + 6
    draw.text((center, footer_y), "Planned with MealGen", font=_font("sans-medium", 22), fill=MUTED, anchor="mm")

    buffer = BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
