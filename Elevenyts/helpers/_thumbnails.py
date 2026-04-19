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
#  ALBUM ART — CIRCLE, CENTERED TOP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ART_W, ART_H = 340, 340
ART_X        = (W - ART_W) // 2
ART_Y        = 40

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BOTTOM DARK CARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CARD_Y = ART_Y + ART_H - 60
CARD_R = 36

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TEXT LAYOUT (all centered)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TITLE_Y   = CARD_Y + 72
ARTIST_Y  = TITLE_Y + 62
VIEWS_Y   = ARTIST_Y + 42

DIVIDER_Y = VIEWS_Y + 42

BAR_X     = 100
BAR_Y     = DIVIDER_Y + 22
BAR_W     = W - 200
BAR_H     = 4
TIME_Y    = BAR_Y + 14

CTRL_Y    = BAR_Y + 52
MARK_Y    = H - 52

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  COLORS — warm gold & dark theme
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
C_TITLE    = (250, 245, 235, 255)
C_ARTIST   = (180, 165, 140, 255)
C_SUBTEXT  = (130, 120, 105, 255)
C_GOLD     = (255, 200, 80,  255)
C_GOLD2    = (220, 100, 40,  255)
C_BAR_TRK  = (60,  55,  45,  180)
C_CARD     = (12,  10,  20,  210)
C_CARD_BR  = (255, 160, 60,  25)
C_CTRL     = (150, 140, 118, 255)
C_MARK     = (255, 170, 50,  160)
C_GLOW1    = (255, 160, 80)
C_GLOW2    = (255, 120, 60)
C_GLOW3    = (255, 180, 100)


class Thumbnail:

    def __init__(self):
        base = "Elevenyts/helpers"
        try:
            # Raleway-Bold — impactful centered title
            self.f_title  = ImageFont.truetype(f"{base}/Raleway-Bold.ttf", 52)
            self.f_artist = ImageFont.truetype(f"{base}/Raleway-Bold.ttf", 32)
            # Inter-Light — all subtitles, times, controls
            self.f_sub    = ImageFont.truetype(f"{base}/Inter-Light.ttf",  26)
            self.f_small  = ImageFont.truetype(f"{base}/Inter-Light.ttf",  21)
            self.f_badge  = ImageFont.truetype(f"{base}/Inter-Light.ttf",  18)
            self.f_ctrl   = ImageFont.truetype(f"{base}/Inter-Light.ttf",  28)
        except Exception as e:
            print(f"[Thumbnail] Font error: {e} — using default")
            _f = ImageFont.load_default()
            self.f_title = self.f_artist = self.f_sub = \
                self.f_small = self.f_badge = self.f_ctrl = _f

    # ── Download ─────────────────────────────────────────
    async def _fetch(self, path: str, url: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                with open(path, "wb") as f:
                    f.write(await resp.read())
        return path

    # ── Entry ────────────────────────────────────────────
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

    # ── Draw ─────────────────────────────────────────────
    def _draw(self, temp: str, output: str, song: Track) -> str:
        try:
            raw = Image.open(temp).convert("RGBA")

            # 1. Blurred song thumbnail as BG (very dark)
            bg = raw.resize((W, H), Image.LANCZOS)
            bg = bg.filter(ImageFilter.GaussianBlur(50))
            bg = ImageEnhance.Brightness(bg).enhance(0.18)

            # 2. Diagonal light streak (top-left to bottom-right)
            streak = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sd     = ImageDraw.Draw(streak, "RGBA")
            for i in range(80):
                alpha = max(0, 16 - i // 4)
                sd.line([(i * 3, 0), (W, H - i * 3)],
                        fill=(255, 220, 180, alpha), width=1)
            bg = Image.alpha_composite(bg, streak)

            # 3. Orange glow rings behind circular art
            cx = ART_X + ART_W // 2
            cy = ART_Y + ART_H // 2
            for (rr, aa, col) in [
                (210, 8,  C_GLOW1),
                (175, 16, C_GLOW2),
                (140, 28, C_GLOW3),
            ]:
                gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(gl, "RGBA").ellipse(
                    (cx - rr, cy - rr, cx + rr, cy + rr),
                    fill=(*col, aa)
                )
                bg = Image.alpha_composite(bg, gl)

            # 4. Circular album art
            art      = raw.resize((ART_W, ART_H), Image.LANCZOS)
            art_mask = Image.new("L", (ART_W, ART_H), 0)
            ImageDraw.Draw(art_mask).ellipse(
                (0, 0, ART_W, ART_H), fill=255
            )
            bg.paste(art, (ART_X, ART_Y), art_mask)

            draw = ImageDraw.Draw(bg, "RGBA")

            # 5. Circle border (gold)
            draw.ellipse(
                (ART_X - 3, ART_Y - 3, ART_X + ART_W + 3, ART_Y + ART_H + 3),
                outline=(255, 180, 80, 55), width=3
            )

            # 6. Bottom frosted dark card
            card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(card, "RGBA").rounded_rectangle(
                (40, CARD_Y, W - 40, H - 30),
                radius=CARD_R,
                fill=C_CARD,
                outline=C_CARD_BR,
                width=1
            )
            bg   = Image.alpha_composite(bg, card)
            draw = ImageDraw.Draw(bg, "RGBA")

            # 7. Song title — CENTERED (Raleway Bold)
            title = song.title.strip()
            if len(title) > 30:
                title = title[:30] + "…"
            tw = int(draw.textlength(title, font=self.f_title))
            draw.text(
                ((W - tw) // 2, TITLE_Y),
                title, fill=C_TITLE, font=self.f_title
            )

            # 8. Artist — centered (Raleway Bold, smaller)
            channel = (
                getattr(song, "channel",  None)
                or getattr(song, "artist",   None)
                or getattr(song, "uploader", None)
                or "Unknown Artist"
            )
            channel = str(channel).strip()
            if not channel or channel.lower() in ("none", ""):
                channel = "Unknown Artist"
            if len(channel) > 40:
                channel = channel[:40] + "…"

            aw = int(draw.textlength(channel, font=self.f_artist))
            draw.text(
                ((W - aw) // 2, ARTIST_Y),
                channel, fill=C_ARTIST, font=self.f_artist
            )

            # 9. Views — centered (Inter Light)
            views = str(getattr(song, "views", "") or "").strip()
            if views and views.lower() not in ("none", "0", ""):
                vtxt = f"{views} views  •  YouTube"
            else:
                vtxt = "YouTube"
            vw = int(draw.textlength(vtxt, font=self.f_small))
            draw.text(
                ((W - vw) // 2, VIEWS_Y),
                vtxt, fill=C_SUBTEXT, font=self.f_small
            )

            # 10. Divider — glowing fade line
            for i in range(BAR_W):
                t     = i / (BAR_W - 1)
                alpha = int(255 * (1 - abs(t - 0.5) * 2))
                draw.point(
                    (BAR_X + i, DIVIDER_Y),
                    fill=(255, 160, 60, max(5, alpha * 55 // 255))
                )

            # 11. Progress bar track
            draw.rounded_rectangle(
                (BAR_X, BAR_Y, BAR_X + BAR_W, BAR_Y + BAR_H),
                radius=2, fill=C_BAR_TRK
            )

            # 12. Gold gradient fill
            bar_progress = int(BAR_W * 0.15)
            for i in range(bar_progress):
                t  = i / max(bar_progress - 1, 1)
                rr = int(255 + (220 - 255) * t * 0.3)
                gg = int(200 + (100 - 200) * t)
                bb = int(80  + (20  - 80)  * t)
                draw.rectangle(
                    (BAR_X + i, BAR_Y, BAR_X + i + 1, BAR_Y + BAR_H),
                    fill=(min(255, rr), min(255, gg), min(255, bb), 255)
                )

            # 13. Gold knob
            kx = BAR_X + bar_progress
            ky = BAR_Y + BAR_H // 2
            draw.ellipse(
                (kx - 8, ky - 8, kx + 8, ky + 8),
                fill=C_GOLD
            )

            # 14. Time labels
            draw.text((BAR_X, TIME_Y), "00:00",
                      fill=C_SUBTEXT, font=self.f_small)
            dur   = str(getattr(song, "duration", "0:00") or "0:00").strip()
            dur_w = int(draw.textlength(dur, font=self.f_small))
            draw.text((BAR_X + BAR_W - dur_w, TIME_Y), dur,
                      fill=C_SUBTEXT, font=self.f_small)

            # 15. Controls — centered
            icons = [("⇄", False), ("⏮", False), ("⏸", True),
                     ("⏭", False), ("↺", False)]
            spc   = 100
            sx    = W // 2 - spc * 2
            for idx, (ic, is_center) in enumerate(icons):
                icx = sx + idx * spc
                if is_center:
                    draw.ellipse(
                        (icx - 24, CTRL_Y - 4, icx + 24, CTRL_Y + 40),
                        fill=(255, 170, 50, 20),
                        outline=(255, 170, 50, 48),
                        width=1
                    )
                col = C_GOLD if is_center else C_CTRL
                iw  = int(draw.textlength(ic, font=self.f_ctrl))
                draw.text(
                    (icx - iw // 2, CTRL_Y),
                    ic, fill=col, font=self.f_ctrl
                )

            # 16. Bot watermark — bottom center
            mark  = "♪  AdamMusicBot"
            mark_w = int(draw.textlength(mark, font=self.f_badge))
            draw.text(
                ((W - mark_w) // 2, MARK_Y),
                mark, fill=C_MARK, font=self.f_badge
            )

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
            
