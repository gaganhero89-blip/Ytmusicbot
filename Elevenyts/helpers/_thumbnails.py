# ============================================================
#   thumbnail.py  —  ADAM MUSIC BOT
#   Generates a "Now Playing" thumbnail for every track.
#
#   pip install Pillow aiohttp
#
#   HOW TO CALL FROM YOUR PLAY HANDLER:
#
#       from thumbnail import generate_thumbnail
#
#       thumb_path = await generate_thumbnail(
#           title     = "Tum Hi Ho",
#           artist    = "Arijit Singh",
#           duration  = 262,          # total seconds  (0 = unknown)
#           elapsed   = 0,            # seconds played (0 at start)
#           thumb_url = "https://i.ytimg.com/vi/xxxx/hqdefault.jpg",
#           source    = "YouTube",    # or "Spotify", "SoundCloud", etc.
#       )
#       await bot.send_photo(chat_id, photo=thumb_path, caption=f"🎵 {title}")
#
# ============================================================

from __future__ import annotations

import asyncio
import math
import os
import random
import textwrap
from io import BytesIO

import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ── Directories ──────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")      # put fonts + logo here
CACHE_DIR  = os.path.join(BASE_DIR, "cache", "thumbs")
os.makedirs(CACHE_DIR,  exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

# ── Font paths  (TTF files in /assets — falls back to PIL default) ────────────
_FONT_BOLD = os.path.join(ASSETS_DIR, "bold.ttf")       # Montserrat-Bold
_FONT_SEMI = os.path.join(ASSETS_DIR, "semibold.ttf")   # Montserrat-SemiBold
_FONT_REG  = os.path.join(ASSETS_DIR, "regular.ttf")    # Montserrat-Regular
_LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")       # ADAM MUSIC BOT logo (RGBA PNG)

# ── Canvas ───────────────────────────────────────────────────────────────────
W, H = 1280, 720

# ── Colour palette ───────────────────────────────────────────────────────────
_BG         = (10,   6,  20)
_PANEL      = (18,  12,  35)
_PINK       = (232,  30, 120)
_PURP       = (150,  60, 230)
_NEON_PINK  = (255,  50, 150)
_NEON_PURP  = (180,  80, 255)
_WHITE      = (255, 255, 255)
_GREY_LIGHT = (180, 170, 200)
_GREY_MID   = (110, 100, 130)
_BAR_TRACK  = ( 60,  45,  80)


# ══════════════════════════════════════════════════════════════════════════════
#   Internal helpers
# ══════════════════════════════════════════════════════════════════════════════

def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a TTF font; silently fall back to PIL built-in on error."""
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.load_default(size=size)   # Pillow 10+
        except TypeError:
            return ImageFont.load_default()


def _text_width(font: ImageFont.FreeTypeFont, text: str) -> int:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def _truncate(text: str, font: ImageFont.FreeTypeFont, max_px: int) -> str:
    """Trim text + '…' so it fits within max_px."""
    if _text_width(font, text) <= max_px:
        return text
    while len(text) > 1:
        text = text[:-1]
        if _text_width(font, text + "…") <= max_px:
            return text + "…"
    return "…"


def _fmt_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _grad_h(draw: ImageDraw.ImageDraw,
            x0: int, y0: int, x1: int, y1: int,
            left: tuple, right: tuple) -> None:
    """Draw a horizontal linear-gradient rectangle."""
    w = x1 - x0
    for i in range(w):
        t = i / max(w - 1, 1)
        r = int(left[0] + t * (right[0] - left[0]))
        g = int(left[1] + t * (right[1] - left[1]))
        b = int(left[2] + t * (right[2] - left[2]))
        draw.line([(x0 + i, y0), (x0 + i, y1)], fill=(r, g, b))


def _rrect(draw: ImageDraw.ImageDraw,
           xy: tuple, radius: int,
           fill=None, outline=None, width: int = 2) -> None:
    draw.rounded_rectangle(list(xy), radius=radius,
                           fill=fill, outline=outline, width=width)


def _fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale + centre-crop to exactly w×h."""
    iw, ih = img.size
    scale  = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img    = img.resize((nw, nh), Image.LANCZOS)
    return img.crop(((nw - w) // 2, (nh - h) // 2,
                     (nw - w) // 2 + w, (nh - h) // 2 + h))


def _round_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius=r, fill=255)
    return mask


def _waveform(draw: ImageDraw.ImageDraw,
              x: int, y: int, w: int, h: int,
              color: tuple, bars: int = 32, seed: int = 7) -> None:
    """Draw a static decorative waveform."""
    rng = random.Random(seed)
    bw  = w // bars
    gap = max(1, bw // 5)
    for i in range(bars):
        bh  = int(rng.uniform(0.2, 1.0) * h)
        bx  = x + i * bw
        alpha = 220 if i > bars // 2 else 120
        c = (*color, alpha)
        # Pillow RGBA draw on RGB → just use fill directly
        draw.rectangle([bx, y + h - bh, bx + bw - gap, y + h], fill=color)


def _draw_progress(draw: ImageDraw.ImageDraw,
                   x: int, y: int, w: int,
                   progress: float,
                   cur_str: str, tot_str: str) -> None:
    track_h = 7
    knob_r  = 11
    # track
    _rrect(draw, (x, y, x + w, y + track_h),
           radius=track_h // 2, fill=_BAR_TRACK)
    # fill
    fill_w = max(knob_r, int(w * progress))
    _grad_h(draw, x, y, x + fill_w, y + track_h, _PINK, _NEON_PURP)
    # knob
    kx, ky = x + fill_w, y + track_h // 2
    draw.ellipse([kx - knob_r, ky - knob_r, kx + knob_r, ky + knob_r],
                 fill=_WHITE)
    draw.ellipse([kx - knob_r + 3, ky - knob_r + 3,
                  kx + knob_r - 3, ky + knob_r - 3], fill=_PINK)
    # timestamps
    ts = _font(_FONT_REG, 28)
    draw.text((x, y + track_h + 12), cur_str, font=ts, fill=_GREY_LIGHT)
    draw.text((x + w, y + track_h + 12), tot_str,
              font=ts, fill=_GREY_LIGHT, anchor="ra")


def _draw_controls(draw: ImageDraw.ImageDraw,
                   cx: int, cy: int) -> None:
    """Draw shuffle / prev / pause / next / repeat buttons."""
    buttons = [
        (cx - 190, 30, "⇄",  False),
        (cx - 105, 30, "⏮",  False),
        (cx,       40, "⏸",  True),   # big primary button
        (cx + 105, 30, "⏭",  False),
        (cx + 190, 30, "↺",  False),
    ]
    for bx, br, sym, primary in buttons:
        border = _PINK if primary else _GREY_MID
        bw     = 3     if primary else 1
        draw.ellipse([bx - br, cy - br, bx + br, cy + br],
                     fill=_BG, outline=border, width=bw)
        if primary:
            # inner glow ring
            draw.ellipse([bx - br + 4, cy - br + 4,
                          bx + br - 4, cy + br - 4],
                         fill=_BG, outline=(*_PINK, 80), width=1)
        sym_f = _font(_FONT_BOLD, br - 6)
        col   = _WHITE if primary else _GREY_LIGHT
        draw.text((bx, cy), sym, font=sym_f, fill=col, anchor="mm")


def _glow_layer(size: tuple, color: tuple,
                radius: int = 200, alpha: int = 80) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw  = ImageDraw.Draw(layer)
    draw.ellipse([size[0] // 2 - radius, -radius // 2,
                  size[0] // 2 + radius,  radius],
                 fill=(*color, alpha))
    return layer.filter(ImageFilter.GaussianBlur(radius // 2))


async def _fetch_art(url: str) -> Image.Image | None:
    """Download remote artwork; return None on any failure."""
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.read()
                    return Image.open(BytesIO(data)).convert("RGB")
    except Exception:
        pass
    return None


def _placeholder_art(w: int, h: int) -> Image.Image:
    """Dark gradient art panel when no thumbnail URL is given."""
    img  = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    _grad_h(draw, 0, 0, w, h, (25, 8, 55), (70, 20, 120))
    # soft spotlight
    spot = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd   = ImageDraw.Draw(spot)
    for r in range(130, 0, -5):
        a = int(50 * (1 - r / 130))
        sd.ellipse([w // 2 - r, h // 2 - r, w // 2 + r, h // 2 + r],
                   fill=(*_PURP, a))
    img = Image.alpha_composite(img.convert("RGBA"), spot).convert("RGB")
    # music note icon
    draw = ImageDraw.Draw(img)
    nf   = _font(_FONT_BOLD, 100)
    draw.text((w // 2, h // 2 - 20), "♪", font=nf,
              fill=(*_NEON_PURP, 160), anchor="mm")
    return img


def _draw_logo(canvas: Image.Image, draw: ImageDraw.ImageDraw,
               x: int, y: int, size: int = 110) -> None:
    """Paste logo PNG if available, else draw a simple SVG-style fallback."""
    try:
        logo = Image.open(_LOGO_PATH).convert("RGBA")
        logo = logo.resize((size, size), Image.LANCZOS)
        canvas.paste(logo, (x, y), logo)
        return
    except Exception:
        pass
    # ── Fallback: draw A-triangle + music note ──────────────────────────────
    cx, cy = x + size // 2, y + size // 2
    half   = size // 2 - 4
    pts    = [(cx, cy - half), (cx - half, cy + half), (cx + half, cy + half)]
    # outer triangle
    draw.polygon(pts, outline=_PURP, fill=None)
    # inner smaller triangle
    shrink = 14
    pts2   = [(cx, cy - half + shrink),
              (cx - half + shrink, cy + half - 6),
              (cx + half - shrink, cy + half - 6)]
    draw.polygon(pts2, outline=(*_NEON_PURP, 100), fill=None)
    # note dot
    nr = 9
    draw.ellipse([cx + half - nr - 10, cy + half - nr,
                  cx + half + nr - 10, cy + half + nr],
                 fill=_NEON_PURP)
    # note stem
    draw.line([(cx + half - 10 + nr, cy + half),
               (cx + half - 10 + nr, cy + half - 30)],
              fill=_NEON_PURP, width=3)
    draw.line([(cx + half - 10 + nr, cy + half - 30),
               (cx + half - 10 + nr + 20, cy + half - 38)],
              fill=_NEON_PURP, width=3)


# ══════════════════════════════════════════════════════════════════════════════
#   Public API
# ══════════════════════════════════════════════════════════════════════════════

async def generate_thumbnail(
    title:       str,
    artist:      str,
    duration:    int = 0,        # total seconds (0 = unknown / live)
    elapsed:     int = 0,        # seconds already played
    thumb_url:   str = "",       # remote artwork URL (yt-dlp thumbnail)
    source:      str = "YouTube",
    output_path: str = "",
) -> str:
    """
    Build a Now-Playing thumbnail PNG and return its absolute file path.

    Parameters
    ----------
    title        : Track title          (dynamic — comes from yt-dlp / Spotify)
    artist       : Artist / uploader    (dynamic)
    duration     : Total length in secs (0 → shows "LIVE")
    elapsed      : Playback position    (usually 0 at song start)
    thumb_url    : Remote image URL for artwork
    source       : Platform label shown on card
    output_path  : Where to save the PNG (auto-named if blank)
    """
    # ── output path ──────────────────────────────────────────────────────────
    if not output_path:
        safe = "".join(c if c.isalnum() else "_" for c in (title or "track"))[:40]
        output_path = os.path.join(CACHE_DIR, f"{safe}.png")

    # ── fonts ────────────────────────────────────────────────────────────────
    f_title  = _font(_FONT_BOLD, 76)
    f_title2 = _font(_FONT_BOLD, 52)   # smaller fallback for long titles
    f_title3 = _font(_FONT_BOLD, 36)   # even smaller
    f_artist = _font(_FONT_SEMI, 46)
    f_source = _font(_FONT_REG,  30)
    f_badge  = _font(_FONT_SEMI, 26)
    f_tag    = _font(_FONT_REG,  22)
    f_bot    = _font(_FONT_BOLD, 50)
    f_botlbl = _font(_FONT_SEMI, 20)

    # ── base canvas ──────────────────────────────────────────────────────────
    canvas = Image.new("RGB", (W, H), _BG)

    # top-centre purple glow
    glow = _glow_layer((W, H), _PURP, radius=280, alpha=70)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), glow).convert("RGB")

    # bottom-left pink glow (subtle)
    glow2 = _glow_layer((W, H), _PINK, radius=180, alpha=30)
    glow2 = glow2.transform(glow2.size, Image.AFFINE, (1,0,-W*0.7, 0,1,-H*0.3))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), glow2).convert("RGB")

    draw = ImageDraw.Draw(canvas)

    # ── TOP BAR ──────────────────────────────────────────────────────────────
    # left badge
    _rrect(draw, (18, 14, 255, 52), 12, fill=_PANEL, outline=_PURP, width=1)
    draw.text((38, 33), "▐▐  HIGH QUALITY AUDIO",
              font=f_badge, fill=_GREY_LIGHT, anchor="lm")

    # centre tagline
    draw.text((W // 2, 33), "F E E L  T H E  B E A T ,  L I V E  T H E  M U S I C",
              font=f_tag, fill=_GREY_MID, anchor="mm")

    # right badge
    _rrect(draw, (W - 220, 14, W - 18, 52), 12,
           fill=_PANEL, outline=_PURP, width=1)
    draw.text((W - 38, 33), "⚡  24/7 MUSIC",
              font=f_badge, fill=_GREY_LIGHT, anchor="rm")

    # ── LEFT ART PANEL ───────────────────────────────────────────────────────
    AX, AY, AW, AH = 30, 66, 450, 510
    AR = 20

    artwork = await _fetch_art(thumb_url)
    if artwork:
        artwork = _fit_cover(artwork, AW, AH)
        # darken
        ov  = Image.new("RGB", (AW, AH), (0, 0, 0))
        artwork = Image.blend(artwork, ov, 0.28)
    else:
        artwork = _placeholder_art(AW, AH)

    canvas.paste(artwork, (AX, AY), _round_mask(AW, AH, AR))

    # glowing border
    draw.rounded_rectangle([AX - 2, AY - 2, AX + AW + 2, AY + AH + 2],
                            radius=AR + 2, outline=_PURP, width=2)

    # waveform strip at bottom of art
    _waveform(draw, AX + 16, AY + AH - 62, AW - 32, 48, _NEON_PINK, bars=38, seed=13)

    # bottom fade on art
    for i in range(80):
        a = int(200 * (i / 80) ** 2)
        draw.line([(AX, AY + AH - i), (AX + AW, AY + AH - i)],
                  fill=(*_BG, a))

    # bot label on art
    draw.text((AX + AW // 2, AY + AH - 68), "ADAM MUSIC BOT",
              font=_font(_FONT_SEMI, 28), fill=_NEON_PURP, anchor="mm")

    # ── RIGHT INFO CARD ───────────────────────────────────────────────────────
    CX, CY = 510, 66
    CW = W - CX - 28
    CH = 510

    _rrect(draw, (CX, CY, CX + CW, CY + CH),
           radius=20, fill=_PANEL, outline=_PURP, width=2)

    # logo (top-right corner of card)
    _draw_logo(canvas, draw, CX + CW - 128, CY + 14, size=112)
    draw.text((CX + CW - 72, CY + 128), "ADAM MUSIC BOT",
              font=_font(_FONT_REG, 17), fill=_GREY_MID, anchor="mm")

    pad = 28   # left padding inside card
    cy  = CY + 26

    # NOW PLAYING pill
    pill_w, pill_h = 210, 38
    _rrect(draw, (CX + pad, cy, CX + pad + pill_w, cy + pill_h),
           radius=pill_h // 2, fill=_PINK)
    draw.ellipse([CX + pad + 12, cy + pill_h // 2 - 7,
                  CX + pad + 26, cy + pill_h // 2 + 7], fill=_WHITE)
    draw.text((CX + pad + 36, cy + pill_h // 2), "NOW PLAYING",
              font=_font(_FONT_BOLD, 20), fill=_WHITE, anchor="lm")
    cy += pill_h + 18

    # ── Song Title (dynamic, auto-size) ──────────────────────────────────────
    max_title_w = CW - 148    # leave room for logo
    raw_title   = title or "Unknown Track"

    for f_t, min_len in [(f_title, 0), (f_title2, 14), (f_title3, 22)]:
        trunc = _truncate(raw_title, f_t, max_title_w)
        draw.text((CX + pad, cy), trunc, font=f_t, fill=_WHITE)
        title_h = f_t.getbbox("Ag")[3] - f_t.getbbox("Ag")[1]
        cy += title_h + 8
        break   # use first font that fits (truncate handles overflow)

    # ── Artist ───────────────────────────────────────────────────────────────
    raw_artist = artist or "Unknown Artist"
    art_trunc  = _truncate(raw_artist, f_artist, CW - 148)
    draw.text((CX + pad, cy), art_trunc, font=f_artist, fill=_NEON_PINK)
    cy += 58

    # ── Source badge ─────────────────────────────────────────────────────────
    src_icon = "▶" if "youtube" in source.lower() else "♪"
    draw.text((CX + pad, cy), f"{src_icon}  {source}  •  Streaming",
              font=f_source, fill=_GREY_LIGHT)
    cy += 46

    # ── Progress bar ─────────────────────────────────────────────────────────
    progress = (elapsed / duration) if duration > 0 else 0.0
    progress = max(0.0, min(1.0, progress))

    cur_str = _fmt_time(elapsed)
    tot_str = "LIVE" if duration == 0 else _fmt_time(duration)

    _draw_progress(draw, CX + pad, cy, CW - 56, progress, cur_str, tot_str)
    cy += 64

    # ── Playback Controls ─────────────────────────────────────────────────────
    ctrl_cx = CX + CW // 2
    _draw_controls(draw, ctrl_cx, cy + 36)

    # ── BOTTOM FEATURE BAR ───────────────────────────────────────────────────
    feat_items = [
        ("▐▐", "HIGH QUALITY\nAUDIO"),
        ("⚡",  "NO LAG\nSTREAMING"),
        ("≡",   "SMART QUEUE\nSYSTEM"),
        ("👥",  "24/7\nONLINE"),
    ]
    bx = 28
    by = H - 88
    bw = 226
    bh = 64
    for icon, label in feat_items:
        _rrect(draw, (bx, by, bx + bw, by + bh), 12,
               fill=_PANEL, outline=_PURP, width=1)
        draw.text((bx + 14, by + bh // 2), icon,
                  font=_font(_FONT_SEMI, 26), fill=_NEON_PURP, anchor="lm")
        for i, line in enumerate(label.split("\n")):
            draw.text((bx + 50, by + 18 + i * 22), line,
                      font=_font(_FONT_SEMI, 18), fill=_GREY_LIGHT)
        bx += bw + 10

    # ── JOIN VOICE CHAT button ────────────────────────────────────────────────
    jx = bx + 10
    jw = W - jx - 28
    _rrect(draw, (jx, by, jx + jw, by + bh), 14,
           fill=_PANEL, outline=_PINK, width=2)
    draw.text((jx + 16, by + bh // 2), "🎧",
              font=_font(_FONT_REG, 30), anchor="lm")
    draw.text((jx + 58, by + 16), "JOIN VOICE CHAT",
              font=_font(_FONT_BOLD, 22), fill=_WHITE)
    draw.text((jx + 58, by + 40), "Enjoy Together",
              font=_font(_FONT_REG, 18), fill=_GREY_MID)

    # ── ADAM MUSIC BOT logo text (bottom-left) ────────────────────────────────
    draw.text((28, H - 28), "ADAM",
              font=f_bot, fill=_WHITE, anchor="lb")
    draw.text((28 + _text_width(f_bot, "ADAM") + 10, H - 28),
              "MUSIC BOT ─────",
              font=_font(_FONT_SEMI, 22), fill=_NEON_PINK, anchor="lb")

    # ── Powered line (centre bottom) ─────────────────────────────────────────
    draw.text((W // 2, H - 10),
              "─── POWERED BY  ADAM MUSIC BOT ───",
              font=_font(_FONT_REG, 18), fill=_GREY_MID, anchor="mb")

    # ── Vignette ─────────────────────────────────────────────────────────────
    vig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vd  = ImageDraw.Draw(vig)
    for i in range(90):
        a = int(130 * (i / 90) ** 2)
        vd.rectangle([i, i, W - i, H - i], outline=(0, 0, 0, a), width=1)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), vig).convert("RGB")

    canvas.save(output_path, "PNG", optimize=True)
    return os.path.abspath(output_path)


# ── Sync wrapper (for non-async contexts) ────────────────────────────────────

def generate_thumbnail_sync(
    title:       str,
    artist:      str,
    duration:    int = 0,
    elapsed:     int = 0,
    thumb_url:   str = "",
    source:      str = "YouTube",
    output_path: str = "",
) -> str:
    """Blocking version of generate_thumbnail."""
    return asyncio.run(generate_thumbnail(
        title, artist, duration, elapsed, thumb_url, source, output_path
    ))


# ═════════════════════════════
