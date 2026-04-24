import os
import math
import asyncio
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from Elevenyts import config
from Elevenyts.helpers import Track


W, H = 1280, 720


class Thumbnail:

    def __init__(self):
        base = "Elevenyts/helpers"
        try:
            self.f_title  = ImageFont.truetype(f"{base}/Raleway-Bold.ttf", 70)
            self.f_artist = ImageFont.truetype(f"{base}/Raleway-Bold.ttf", 40)
            self.f_small  = ImageFont.truetype(f"{base}/Inter-Light.ttf", 24)
            self.f_badge  = ImageFont.truetype(f"{base}/Inter-Light.ttf", 20)
        except:
            f = ImageFont.load_default()
            self.f_title = self.f_artist = self.f_small = self.f_badge = f

    async def _fetch(self, path, url):
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _draw(self, temp, output, song):
        raw = Image.open(temp).convert("RGBA")

        # ── BACKGROUND ──
        bg = raw.resize((W, H))
        bg = bg.filter(ImageFilter.GaussianBlur(60))
        bg = ImageEnhance.Brightness(bg).enhance(0.15)

        overlay = Image.new("RGBA", (W, H), (10, 5, 25, 220))
        bg = Image.alpha_composite(bg, overlay)

        draw = ImageDraw.Draw(bg, "RGBA")

        # ── TOP BAR ──
        draw.rounded_rectangle((60,30,300,80), 20,
            fill=(255,255,255,10), outline=(255,120,255,80))
        draw.text((90,45), "HIGH QUALITY\nAUDIO",
            fill=(220,180,255), font=self.f_small)

        draw.rounded_rectangle((980,30,1220,80), 20,
            fill=(255,255,255,10), outline=(255,120,255,80))
        draw.text((1020,45), "24/7\nMUSIC",
            fill=(220,180,255), font=self.f_small)

        tag = "FEEL THE BEAT, LIVE THE MUSIC"
        tw = int(draw.textlength(tag, font=self.f_small))
        draw.text(((W-tw)//2, 50), tag,
            fill=(200,160,255,180), font=self.f_small)

        # ── ALBUM ART ──
        art = raw.resize((420,420))
        mask = Image.new("L",(420,420),0)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,420,420),40,fill=255)
        bg.paste(art,(60,140),mask)

        # glow border
        glow = Image.new("RGBA",(W,H),(0,0,0,0))
        gd = ImageDraw.Draw(glow)
        gd.rounded_rectangle((60,140,480,560),40,
            outline=(255,80,200,120), width=3)
        bg = Image.alpha_composite(bg, glow)

        draw = ImageDraw.Draw(bg,"RGBA")

        # ── RIGHT PANEL ──
        draw.rounded_rectangle((520,120,1240,600),30,
            fill=(255,255,255,8), outline=(255,255,255,20))

        # ── NOW PLAYING ──
        draw.rounded_rectangle((560,140,760,175),18,
            fill=(255,70,120,220))
        draw.text((585,148),"NOW PLAYING",
            fill=(255,255,255),font=self.f_badge)

        # ── TITLE ──
        title = song.title[:22] + "…" if len(song.title)>22 else song.title
        draw.text((560,200), title,
            fill=(255,255,255), font=self.f_title)

        # ── ARTIST ──
        artist = getattr(song,"artist",None) or "Adam Music Bot"
        draw.text((560,280), artist,
            fill=(200,150,255), font=self.f_artist)

        # ── PROGRESS BAR ──
        bx, by, bw = 560, 360, 520
        draw.rounded_rectangle((bx,by,bx+bw,by+6),4,
            fill=(60,60,80))

        prog = int(bw*0.3)
        for i in range(prog):
            t=i/prog
            color=(int(255*(1-t)+180*t),80,int(150*(1-t)+255*t))
            draw.rectangle((bx+i,by,bx+i+1,by+6),fill=color)

        draw.ellipse((bx+prog-8,by-6,bx+prog+8,by+10),
            fill=(255,255,255))

        # time
        draw.text((bx,by+12),"00:45",
            fill=(150,150,200),font=self.f_small)
        draw.text((bx+bw-70,by+12), song.duration,
            fill=(150,150,200),font=self.f_small)

        # ── CONTROLS ──
        cx = bx + bw//2
        draw.ellipse((cx-35,440-35,cx+35,440+35),
            fill=(255,80,200,40))
        draw.ellipse((cx-28,440-28,cx+28,440+28),
            fill=(255,255,255))
        draw.rectangle((cx-8,430,cx-2,450),fill=(20,20,40))
        draw.rectangle((cx+2,430,cx+8,450),fill=(20,20,40))

        # ── WAVEFORM ──
        for i in range(18):
            h = 10 + (i%5)*8
            x = 1100 + i*8
            draw.rectangle((x,380-h,x+4,380+h),
                fill=(200,100,255,180))

        # ── FEATURE BAR ──
        fy=520
        draw.rounded_rectangle((520,fy,1240,fy+80),25,
            fill=(255,255,255,10))

        feats=["HIGH QUALITY","NO LAG","SMART QUEUE","24/7"]
        x=560
        for f in feats:
            draw.text((x,fy+25),f,
                fill=(220,180,255),font=self.f_small)
            x+=180

        # ── BIG BRAND ──
        draw.text((80,600),"ADAM",
            fill=(255,120,220),font=self.f_title)
        draw.text((80,660),"MUSIC BOT",
            fill=(200,150,255),font=self.f_artist)

        # ── JOIN BOX ──
        draw.rounded_rectangle((850,610,1240,700),25,
            fill=(255,255,255,10),
            outline=(255,120,255,120))
        draw.text((900,640),"JOIN VOICE CHAT",
            fill=(255,180,255),font=self.f_artist)
        draw.text((900,675),"Enjoy Together",
            fill=(180,150,220),font=self.f_small)

        # ── SAVE ──
        bg.convert("RGB").save(output,"PNG",optimize=True)

        try: os.remove(temp)
        except: pass

        return output
