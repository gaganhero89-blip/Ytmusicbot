import os
import asyncio
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

from Elevenyts import config
from Elevenyts.helpers import Track

W, H = 1280, 720

class Thumbnail:

    def __init__(self):
        try:
            self.title_font  = ImageFont.truetype("arial.ttf", 58)
            self.artist_font = ImageFont.truetype("arial.ttf", 34)
            self.small_font  = ImageFont.truetype("arial.ttf", 22)
        except:
            self.title_font = self.artist_font = self.small_font = ImageFont.load_default()

    async def _fetch(self, path, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                with open(path, "wb") as f:
                    f.write(await r.read())
        return path

    async def generate(self, song: Track):
        os.makedirs("cache", exist_ok=True)

        temp = f"cache/{song.id}.jpg"
        out  = f"cache/{song.id}.png"

        if os.path.exists(out):
            return out

        await self._fetch(temp, song.thumbnail)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._draw, temp, out, song)

    def _draw(self, temp, out, song):
        raw = Image.open(temp).convert("RGB")

        # ─── BACKGROUND ───
        bg = raw.resize((W, H))
        bg = bg.filter(ImageFilter.GaussianBlur(30))
        bg = ImageEnhance.Brightness(bg).enhance(0.4)

        overlay = Image.new("RGBA", (W, H), (10, 10, 25, 180))
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay)

        draw = ImageDraw.Draw(bg)

        # ─── ALBUM ART ───
        art = raw.resize((400, 400))
        mask = Image.new("L", (400, 400), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,400,400), radius=30, fill=255)
        bg.paste(art, (80, 160), mask)

        # ─── GLASS PANEL ───
        panel = Image.new("RGBA", (650, 450), (255,255,255,20))
        pd = ImageDraw.Draw(panel)
        pd.rounded_rectangle((0,0,650,450), radius=25, outline=(255,255,255,40))
        bg.paste(panel, (520, 130), panel)

        draw = ImageDraw.Draw(bg)

        # ─── TEXT ───
        title = song.title[:22]
        artist = getattr(song, "artist", "Unknown")

        draw.text((550, 170), "NOW PLAYING", font=self.small_font, fill=(255,100,140))
        draw.text((550, 210), title, font=self.title_font, fill=(255,255,255))
        draw.text((550, 280), artist, font=self.artist_font, fill=(180,180,255))

        # ─── PROGRESS BAR (GRADIENT) ───
        bar_x, bar_y = 550, 360
        bar_w = 500

        draw.rectangle((bar_x, bar_y, bar_x+bar_w, bar_y+6), fill=(70,70,90))

        progress = int(bar_w * 0.25)

        for i in range(progress):
            r = int(255 - (i/progress)*80)
            g = int(80)
            b = int(150 + (i/progress)*80)
            draw.rectangle((bar_x+i, bar_y, bar_x+i+1, bar_y+6), fill=(r,g,b))

        # knob
        draw.ellipse((bar_x+progress-8, bar_y-6, bar_x+progress+8, bar_y+10), fill=(255,255,255))

        # ─── TIME ───
        draw.text((bar_x, bar_y+12), "00:45", font=self.small_font, fill=(160,160,200))
        draw.text((bar_x+bar_w-60, bar_y+12), song.duration, font=self.small_font, fill=(160,160,200))

        # ─── PLAY BUTTON ───
        cx = bar_x + bar_w//2
        cy = bar_y + 90

        # glow
        for r,a in [(40,40),(30,60),(20,100)]:
            glow = Image.new("RGBA", (W,H), (0,0,0,0))
            gd = ImageDraw.Draw(glow)
            gd.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(255,80,150,a))
            bg = Image.alpha_composite(bg, glow)

        draw = ImageDraw.Draw(bg)

        # button
        draw.ellipse((cx-25, cy-25, cx+25, cy+25), fill=(255,80,150))

        # pause icon
        draw.rectangle((cx-6, cy-10, cx-2, cy+10), fill=(0,0,0))
        draw.rectangle((cx+2, cy-10, cx+6, cy+10), fill=(0,0,0))

        # ─── SAVE ───
        bg.convert("RGB").save(out, "PNG", quality=95)

        try:
            os.remove(temp)
        except:
            pass

        return out
