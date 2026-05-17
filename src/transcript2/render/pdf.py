"""Offline PDF renderer (Pillow).

A self-contained fallback so a polished PDF exists without Canva or
LibreOffice. Mirrors the PPTX aesthetic: 16:9, navy/gold, JP-safe font.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..schema import Deck, Slide

W, H = 1600, 900
NAVY = (11, 31, 58)
SLATE = (28, 61, 90)
GOLD = (201, 162, 39)
WHITE = (255, 255, 255)
LIGHT = (242, 242, 242)
INK = (32, 40, 54)

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]


def _font_path() -> str:
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return p
    raise RuntimeError("No CJK-capable font found for PDF rendering")


_FP: str | None = None


def _f(size: int) -> ImageFont.FreeTypeFont:
    global _FP
    if _FP is None:
        _FP = _font_path()
    return ImageFont.truetype(_FP, size)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    """Character-wrap (Japanese has no spaces)."""
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if draw.textlength(cur + ch, font=font) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def _title_page(deck: Deck) -> Image.Image:
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 560, W, 566], fill=GOLD)
    for i, ln in enumerate(_wrap(d, deck.title or "プレゼンテーション", _f(54), W - 240)):
        d.text((120, 280 + i * 74), ln, font=_f(54), fill=WHITE)
    if deck.subtitle:
        d.text((120, 600), deck.subtitle[:60], font=_f(26), fill=LIGHT)
    if deck.meta:
        d.text((120, 820), f"出典: {deck.meta.url}", font=_f(18), fill=(150, 160, 175))
    return img


def _section_page(s: Slide) -> Image.Image:
    img = Image.new("RGB", (W, H), SLATE)
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(_wrap(d, s.title, _f(46), W - 240)):
        d.text((120, 330 + i * 64), ln, font=_f(46), fill=WHITE)
    if s.message:
        d.text((120, 500), s.message[:70], font=_f(24), fill=LIGHT)
    return img


def _content_page(s: Slide) -> Image.Image:
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 14, H], fill=GOLD)

    y = 60
    for ln in _wrap(d, s.title, _f(40), W - 180):
        d.text((70, y), ln, font=_f(40), fill=NAVY)
        y += 54
    if s.message:
        y += 8
        for ln in _wrap(d, s.message, _f(24), W - 180):
            d.text((70, y), ln, font=_f(24), fill=GOLD)
            y += 34

    has_img = bool(s.image_path and Path(s.image_path).exists())
    body_w = (W - 560) if has_img else (W - 180)
    y += 30
    for b in s.bullets:
        for j, ln in enumerate(_wrap(d, b, _f(26), body_w - 40)):
            prefix = "●  " if j == 0 else "    "
            d.text((80, y), prefix + ln, font=_f(26), fill=INK)
            y += 40
        y += 12

    if has_img:
        try:
            im = Image.open(s.image_path).convert("RGB")
            im.thumbnail((460, 320))
            img.paste(im, (W - 520, 220))
        except Exception:
            pass
    return img


def render_pdf(deck: Deck, out_path: Path) -> Path:
    pages: list[Image.Image] = []
    for i, s in enumerate(deck.slides):
        if i == 0 or s.layout == "title":
            pages.append(_title_page(deck) if i == 0 else _section_page(s))
        elif s.layout in ("section", "closing"):
            pages.append(_section_page(s))
        else:
            pages.append(_content_page(s))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(
        str(out_path), "PDF", resolution=150,
        save_all=True, append_images=pages[1:],
    )
    return out_path
