import os
import math
import asyncio
import aiohttp
from PIL import (
    Image, ImageDraw, ImageEnhance,
    ImageFilter, ImageFont
)

from Elevenyts import config
from Elevenyts.helpers import Track

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CANVAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
W, H = 1280, 720

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ALBUM ART — LEFT SIDE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ART_W, ART_H = 440, 440
ART_X        = 55
ART_Y        = (H - ART_H) // 2
ART_R        = 32

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  INFO PANEL — RIGHT SIDE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PANEL_X  = 530
PANEL_Y  = 60
PANEL_X2 = W - 30
PANEL_Y2 = H - 50

IX = 570    # text left edge
IY = 100    # text top

BADGE_X, BADGE_Y = IX, IY
TITLE_Y          = IY + 60
ARTIST_Y         = TITLE_Y + 72
VIEWS_Y          = ARTIST_Y + 62

BAR_X  = IX
BAR_Y  = VIEWS_Y + 62
BAR_W  = 580
BAR_H  = 5
TIME_Y = BAR_Y + 14

CTRL_Y = BAR_Y + 56

WF_X   = BAR_X + BAR_W + 22   # waveform start x
WF_Y   = BAR_Y - 30           # waveform center y

MARK_X = 60
MARK_Y = H - 50

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  COLORS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
C_TITLE    = (240, 240, 255, 255)
C_ARTIST   = (180, 175, 210, 255)
C_SUBTEXT  = (155, 150, 190, 200)
C_TIME     = (120, 115, 155, 220)
C_CTRL     = (130, 125, 165, 220)
C_BADGE_BG = (255, 60,  90,  220)
C_BADGE_TX = (255, 255, 255, 255)
C_BADGE_DT = (255, 200, 200, 255)
C_BAR_TRK  = (60,  55,  80,  180)
C_GRAD_A   = (255, 60,  100, 255)   # pink
C_GRAD_B   = (180, 80,  255, 255)   # violet
C_GLOW     = (200, 120, 255)
C_KNOB     = (255, 255, 255, 255)
C_MARK     = (160, 140, 210, 160)
C_PANEL    = (255, 255, 255, 8)
C_PANEL_BR = (255, 255, 255, 12)
C_VIEW_BR  = (255, 255, 255, 40)
C_VIEW_DOT = (120, 115, 160, 180)


class Thumbnail:

    def __init__(self):
        base = "Elevenyts/helpers"
        try:
            self.f_title  = ImageFont.truetype(f"{base}/Raleway-Bold.ttf", 60)
            self.f_artist = ImageFont.truetype(f"{base}/Raleway-Bold.ttf", 38)
            self.f_small  = ImageFont.truetype(f"{base}/Inter-Light.ttf",  22)
            self.f_badge  = ImageFont.truetype(f"{base}/Inter-Light.ttf",  18)
            self.f_mark   = ImageFont.truetype(f"{base}/Inter-Light.ttf",  20)
        except Exception as e:
            print(f"[Thumbnail] Font error: {e} — using default")
            _f = ImageFont.load_default()
            self.f_title = self.f_artist = self.f_small = \
                self.f_badge = self.f_mark = _f

    # ── Download YouTube thumbnail ───────────────────────
    async def _fetch(self, path: str, url: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                with open(path, "wb") as f:
                    f.write(await resp.read())
        return path

    # ── Public entry ─────────────────────────────────────
    async def generate(self, song: Track) -> str:
        try:
            os.makedirs("cache", exist_ok=True)
            temp   = f"cache/{song.id}_raw.jpg"
            output = f"cache/{song.id}_card.png"

            if os.path.exists(output):
                return output

            await self._fetch(temp, song.thumbnail)

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._draw, temp, output, song
            )
        except Exception as e:
            print(f"[Thumbnail] generate() error: {e}")
            return config.DEFAULT_THUMB

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  DRAW
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _draw(self, temp: str, output: str, song: Track) -> str:
        try:
            raw = Image.open(temp).convert("RGBA")

            # ── 1. Dark purple/navy background ───────────
            bg = raw.resize((W, H), Image.LANCZOS)
            bg = bg.filter(ImageFilter.GaussianBlur(55))
            bg = ImageEnhance.Brightness(bg).enhance(0.18)

            # Deep navy tint overlay
            tint = Image.new("RGBA", (W, H), (12, 6, 28, 200))
            bg   = Image.alpha_composite(bg, tint)

            # ── 2. Subtle color bleed from art ────────────
            bleed = raw.resize((W, H), Image.LANCZOS)
            bleed = bleed.filter(ImageFilter.GaussianBlur(80))
            bleed = ImageEnhance.Brightness(bleed).enhance(0.10)
            bleed_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            bleed_layer.paste(bleed, (0, 0))
            bg = Image.alpha_composite(bg, bleed_layer)

            # ── 3. Glass panel (right) ────────────────────
            glass = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(glass, "RGBA").rounded_rectangle(
                (PANEL_X, PANEL_Y, PANEL_X2, PANEL_Y2),
                radius=28, fill=C_PANEL, outline=C_PANEL_BR, width=1
            )
            bg = Image.alpha_composite(bg, glass)

            # ── 4. Album art — rounded rectangle ─────────
            art      = raw.resize((ART_W, ART_H), Image.LANCZOS)
            art_mask = Image.new("L", (ART_W, ART_H), 0)
            ImageDraw.Draw(art_mask).rounded_rectangle(
                (0, 0, ART_W, ART_H), radius=ART_R, fill=255
            )
            bg.paste(art, (ART_X, ART_Y), art_mask)

            # Art border
            ab = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(ab).rounded_rectangle(
                (ART_X, ART_Y, ART_X + ART_W, ART_Y + ART_H),
                radius=ART_R, outline=(255, 255, 255, 18), width=2
            )
            bg   = Image.alpha_composite(bg, ab)
            draw = ImageDraw.Draw(bg, "RGBA")

            # ── 5. NOW PLAYING badge (PIL drawn) ──────────
            BDW, BDH = 210, 36
            draw.rounded_rectangle(
                (BADGE_X, BADGE_Y, BADGE_X + BDW, BADGE_Y + BDH),
                radius=18, fill=C_BADGE_BG
            )
            # Red dot
            draw.ellipse(
                (BADGE_X + 14, BADGE_Y + 11,
                 BADGE_X + 26, BADGE_Y + 25),
                fill=C_BADGE_DT
            )
            # "NOW PLAYING" text
            draw.text(
                (BADGE_X + 34, BADGE_Y + 9),
                "NOW PLAYING",
                fill=C_BADGE_TX, font=self.f_badge
            )

            # ── 6. Song title ─────────────────────────────
            title = song.title.strip()
            if len(title) > 24:
                title = title[:24] + "…"
            draw.text((IX, TITLE_Y), title,
                      fill=C_TITLE, font=self.f_title)

            # ── 7. Artist / channel ───────────────────────
            channel = (
                getattr(song, "channel",  None)
                or getattr(song, "artist",   None)
                or getattr(song, "uploader", None)
                or getattr(song, "author",   None)
                or ""
            )
            channel = str(channel).strip()
            if not channel or channel.lower() in ("none", "unknown artist", "unknown", ""):
                raw_title = song.title.strip()
                found = ""
                for sep in ["|", "—", "-"]:
                    if sep in raw_title:
                        parts     = raw_title.split(sep, 1)
                        candidate = parts[1].strip()
                        if len(candidate) > 2:
                            found = candidate
                            break
                channel = found if found else "Adam Music Bot"
            if len(channel) > 36:
                channel = channel[:36] + "…"

            draw.text((IX, ARTIST_Y), channel,
                      fill=C_ARTIST, font=self.f_artist)

            # ── 8. Views pill (PIL drawn, no unicode) ─────
            views = str(getattr(song, "views", "") or "").strip()
            views_str = f"{views} views" if views and views.lower() not in ("none", "0", "") else ""

            VX, VY = IX, VIEWS_Y
            # Eye icon (circle + pupil)
            draw.ellipse((VX + 8, VY + 9, VX + 26, VY + 23),
                         outline=(*C_VIEW_DOT[:3], 180), width=2)
            draw.ellipse((VX + 14, VY + 13, VX + 20, VY + 19),
                         fill=(*C_VIEW_DOT[:3], 180))

            tx = VX + 32
            if views_str:
                draw.text((tx, VY + 6), views_str,
                          fill=C_SUBTEXT, font=self.f_small)
                vw2 = int(draw.textlength(views_str, font=self.f_small))
                # Dot separator
                draw.ellipse(
                    (tx + vw2 + 8, VY + 14, tx + vw2 + 14, VY + 20),
                    fill=C_VIEW_DOT
                )
                draw.text((tx + vw2 + 20, VY + 6), "YouTube",
                          fill=C_SUBTEXT, font=self.f_small)
                # Border around pill
                pill_w = vw2 + 80
                draw.rounded_rectangle(
                    (VX, VY + 2, VX + pill_w, VY + 30),
                    radius=14, outline=C_VIEW_BR, width=1
                )
            else:
                draw.text((tx, VY + 6), "YouTube",
                          fill=C_SUBTEXT, font=self.f_small)

            # ── 9. Progress bar track ─────────────────────
            draw.rounded_rectangle(
                (BAR_X, BAR_Y, BAR_X + BAR_W, BAR_Y + BAR_H),
                radius=3, fill=C_BAR_TRK
            )

            # ── 10. Pink → violet gradient fill ──────────
            bar_progress = int(BAR_W * 0.15)
            for i in range(bar_progress):
                t  = i / max(bar_progress - 1, 1)
                rr = int(C_GRAD_A[0] + (C_GRAD_B[0] - C_GRAD_A[0]) * t)
                gg = int(C_GRAD_A[1] + (C_GRAD_B[1] - C_GRAD_A[1]) * t)
                bb = int(C_GRAD_A[2] + (C_GRAD_B[2] - C_GRAD_A[2]) * t)
                draw.rectangle(
                    (BAR_X + i, BAR_Y, BAR_X + i + 1, BAR_Y + BAR_H),
                    fill=(rr, gg, bb, 255)
                )

            # ── 11. Knob with glow ────────────────────────
            kx = BAR_X + bar_progress
            ky = BAR_Y + BAR_H // 2
            kg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            kgd = ImageDraw.Draw(kg, "RGBA")
            for rr, aa in [(20, 12), (14, 22), (9, 40)]:
                kgd.ellipse(
                    (kx - rr, ky - rr, kx + rr, ky + rr),
                    fill=(*C_GLOW, aa)
                )
            bg   = Image.alpha_composite(bg, kg)
            draw = ImageDraw.Draw(bg, "RGBA")
            draw.ellipse((kx - 10, ky - 10, kx + 10, ky + 10),
                         fill=C_KNOB)

            # ── 12. Time labels ───────────────────────────
            draw.text((BAR_X, TIME_Y), "00:00",
                      fill=C_TIME, font=self.f_small)
            dur   = str(getattr(song, "duration", "0:00") or "0:00").strip()
            dur_w = int(draw.textlength(dur, font=self.f_small))
            draw.text((BAR_X + BAR_W - dur_w, TIME_Y), dur,
                      fill=C_TIME, font=self.f_small)

            # ── 13. Waveform bars (right of bar) ──────────
            self._waveform(draw, WF_X, WF_Y + 55)

            # ── 14. Controls (all PIL shapes) ─────────────
            cy2 = CTRL_Y + 18
            spc = 90
            sx  = BAR_X + BAR_W // 2 - spc * 2
            self._draw_shuffle(draw, sx + 0 * spc, cy2, C_CTRL)
            self._draw_prev   (draw, sx + 1 * spc, cy2, C_CTRL)
            self._draw_pause  (draw, sx + 2 * spc, cy2)
            self._draw_next   (draw, sx + 3 * spc, cy2, C_CTRL)
            self._draw_repeat (draw, sx + 4 * spc, cy2, C_CTRL)

            # ── 15. Watermark ─────────────────────────────
            draw.text((MARK_X, MARK_Y), "Adam Music Bot",
                      fill=C_MARK, font=self.f_mark)

            # Save
            bg.convert("RGB").save(output, "PNG", optimize=True)
            try:
                os.remove(temp)
            except OSError:
                pass

            return output

        except Exception as e:
            print(f"[Thumbnail] _draw() error: {e}")
            return config.DEFAULT_THUMB

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  WAVEFORM
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _waveform(self, draw: ImageDraw.ImageDraw, x: int, cy: int) -> None:
        heights = [18, 32, 24, 45, 30, 52, 36, 44, 22, 40, 28, 50, 20, 38, 26, 48]
        for i, bh in enumerate(heights):
            bx    = x + i * 14
            alpha = int(80 + 100 * (i / len(heights)))
            draw.rounded_rectangle(
                (bx, cy - bh // 2, bx + 6, cy + bh // 2),
                radius=3,
                fill=(150, 100, 255, alpha)
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  CONTROL SHAPES (no unicode/emoji)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _draw_shuffle(self, draw, x, y, col):
        """Two crossing arrows — shuffle icon"""
        draw.line([(x - 14, y - 6), (x + 14, y - 6)], fill=col, width=2)
        draw.polygon([(x + 10, y - 11), (x + 17, y - 6), (x + 10, y - 1)], fill=col)
        draw.line([(x + 14, y + 6), (x - 14, y + 6)], fill=col, width=2)
        draw.polygon([(x - 10, y + 11), (x - 17, y + 6), (x - 10, y + 1)], fill=col)

    def _draw_prev(self, draw, x, y, col):
        """Bar + left triangle — previous icon"""
        draw.rectangle((x - 15, y - 13, x - 9, y + 13), fill=col)
        draw.polygon([(x + 13, y - 13), (x - 8, y), (x + 13, y + 13)], fill=col)

    def _draw_pause(self, draw, x, y):
        """Circle + two bars — pause icon (gold circle)"""
        draw.ellipse(
            (x - 24, y - 24, x + 24, y + 24),
            fill=(255, 255, 255, 255)
        )
        draw.rectangle((x - 9, y - 10, x - 3, y + 10), fill=(16, 12, 32, 255))
        draw.rectangle((x + 3, y - 10, x + 9, y + 10), fill=(16, 12, 32, 255))

    def _draw_next(self, draw, x, y, col):
        """Right triangle + bar — next icon"""
        draw.polygon([(x - 13, y - 13), (x + 8, y), (x - 13, y + 13)], fill=col)
        draw.rectangle((x + 9, y - 13, x + 15, y + 13), fill=col)

    def _draw_repeat(self, draw, x, y, col):
        """Circular arc + arrow — repeat icon"""
        for angle in range(20, 340, 5):
            a   = math.radians(angle)
            px2 = int(x + 13 * math.cos(a))
            py2 = int(y + 13 * math.sin(a))
            draw.ellipse((px2 - 1, py2 - 1, px2 + 2, py2 + 2), fill=col)
        draw.polygon(
            [(x + 11, y - 5), (x + 18, y), (x + 11, y + 5)],
            fill=col
)
            
