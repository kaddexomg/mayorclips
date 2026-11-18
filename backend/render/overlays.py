import re
from pathlib import Path
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
FONT_EMOJI = r"C:\Windows\Fonts\seguiemj.ttf"

# Regex matching Unicode emoji characters (including variation selectors and ZWJ)
_EMOJI_RE = re.compile(
    "(["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F2FF"
    "][\uFE0F\u200D\U0001F3FB-\U0001F3FF]*)"
)


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _tokenize_inline(text: str) -> List[Tuple[str, bool]]:
    """Splits text into (segment, is_emoji) tokens while preserving spaces."""
    parts = _EMOJI_RE.split(text)
    tokens: List[Tuple[str, bool]] = []
    for p in parts:
        if not p:
            continue
        is_em = bool(_EMOJI_RE.fullmatch(p))
        if is_em:
            tokens.append((p, True))
        else:
            # Split by words preserving spaces
            for m in re.finditer(r"\S+\s*|\s+", p):
                tokens.append((m.group(0), False))
    return tokens


def _measure_token(draw: ImageDraw.ImageDraw, token: str, is_emoji: bool, text_font, emoji_font) -> int:
    font = emoji_font if is_emoji else text_font
    bbox = draw.textbbox((0, 0), token, font=font)
    return max(0, bbox[2] - bbox[0])


def _layout_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    text_font,
    emoji_font,
) -> List[Tuple[List[Tuple[str, bool, int]], int]]:
    tokens = _tokenize_inline(text)
    lines = []
    cur_line = []
    cur_w = 0

    for tok, is_em in tokens:
        tw = _measure_token(draw, tok, is_em, text_font, emoji_font)
        if cur_line and cur_w + tw > max_width and tok.strip():
            # Strip trailing space width for mathematically exact centering
            while cur_line and not cur_line[-1][0].strip():
                _, _, sw = cur_line.pop()
                cur_w -= sw
            lines.append((cur_line, cur_w))
            cur_line = []
            cur_w = 0
            if not tok.strip():
                continue
        cur_line.append((tok, is_em, tw))
        cur_w += tw

    if cur_line:
        while cur_line and not cur_line[-1][0].strip():
            _, _, sw = cur_line.pop()
            cur_w -= sw
        lines.append((cur_line, cur_w))
    return lines


def render_pill_overlay_png(
    text: str,
    out_path: str,
    y_center: int = 310,
    font_size: int = 50,
    max_text_width: int = 840,
    bg_rgba: Tuple[int, int, int, int] = (6, 11, 16, 228),
    border_rgba: Tuple[int, int, int, int] = (43, 240, 200, 165),
    text_rgba: Tuple[int, int, int, int] = (248, 250, 252, 255),
) -> Optional[str]:
    """Draws a crisp 1080x1920 transparent PNG overlay with rounded glass card, exact centering, and color emojis."""
    clean = (text or "").strip().strip("[]").strip()
    if not clean:
        return None

    img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    text_font = _load_font(FONT_BOLD, font_size)
    emoji_font = _load_font(FONT_EMOJI, int(font_size * 0.95))

    lines = _layout_lines(draw, clean, max_text_width, text_font, emoji_font)
    if not lines:
        return None

    line_h = int(font_size * 1.32)
    max_line_w = max(w for _, w in lines)
    pad_x = 42
    pad_y = 24
    box_w = min(960, max_line_w + pad_x * 2)
    box_h = len(lines) * line_h + pad_y * 2

    x0 = (1080 - box_w) // 2
    y0 = y_center - box_h // 2
    x1 = x0 + box_w
    y1 = y0 + box_h

    # Soft drop shadow
    draw.rounded_rectangle([x0 + 4, y0 + 8, x1 + 4, y1 + 8], radius=28, fill=(0, 0, 0, 120))
    # Glass dark card
    draw.rounded_rectangle([x0, y0, x1, y1], radius=28, fill=bg_rgba, outline=border_rgba, width=3)

    # Render centered lines with inline color emojis
    cur_y = y0 + pad_y - int(font_size * 0.1)
    for line_tokens, line_w in lines:
        cur_x = (1080 - line_w) // 2
        for tok, is_em, tw in line_tokens:
            if is_em:
                draw.text((cur_x, cur_y + 4), tok, font=emoji_font, embedded_color=True)
            else:
                draw.text((cur_x, cur_y), tok, font=text_font, fill=text_rgba)
            cur_x += tw
        cur_y += line_h

    img.save(out_path, "PNG")
    return out_path
