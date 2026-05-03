import asyncio
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pyrogram import enums, filters, types

from Elevenyts import app, config, db, lang

# Font paths
FONT_REGULAR = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"


def is_emoji(char: str) -> bool:
    """Check if a character is an emoji."""
    cp = ord(char)
    return (
        0x1F600 <= cp <= 0x1F64F or
        0x1F300 <= cp <= 0x1F5FF or
        0x1F680 <= cp <= 0x1F6FF or
        0x1F1E0 <= cp <= 0x1F1FF or
        0x2600 <= cp <= 0x26FF or
        0x2700 <= cp <= 0x27BF or
        0x1F900 <= cp <= 0x1F9FF or
        0x1FA00 <= cp <= 0x1FA9F or
        0x1FA70 <= cp <= 0x1FAFF
    )


def split_text_emoji(text: str):
    """Split text into (type, value) parts: 'text' or 'emoji'."""
    parts = []
    buf = ""
    buf_type = "text"
    for ch in text:
        t = "emoji" if is_emoji(ch) else "text"
        if t == buf_type:
            buf += ch
        else:
            if buf:
                parts.append((buf_type, buf))
            buf = ch
            buf_type = t
    if buf:
        parts.append((buf_type, buf))
    return parts


def draw_text_with_emoji(
    img: Image.Image,
    text: str,
    pos: tuple,
    text_font,
    emoji_size: int = 26,
    text_color: tuple = (180, 180, 255),
):
    """Draw text supporting both Unicode special chars and color emojis."""
    draw = ImageDraw.Draw(img)
    try:
        efont = ImageFont.truetype(EMOJI_FONT, 109)
    except Exception:
        efont = None

    x, y = pos
    parts = split_text_emoji(text)

    for kind, val in parts:
        if kind == "text":
            draw.text((x, y), val, font=text_font, fill=text_color)
            x += draw.textlength(val, font=text_font)
        else:
            for ec in val:
                if efont:
                    try:
                        tmp = Image.new("RGBA", (109, 109), (0, 0, 0, 0))
                        tmp_draw = ImageDraw.Draw(tmp)
                        tmp_draw.text((0, 0), ec, font=efont, embedded_color=True)
                        tmp = tmp.resize((emoji_size, emoji_size), Image.LANCZOS)
                        img.paste(tmp, (int(x), int(y) - 2), tmp)
                    except Exception:
                        pass
                x += emoji_size + 2


def text_width_with_emoji(text: str, text_font, emoji_size: int = 26) -> float:
    """Calculate total width of text including emojis."""
    dummy = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy)
    parts = split_text_emoji(text)
    total = 0
    for kind, val in parts:
        if kind == "text":
            total += draw.textlength(val, font=text_font)
        else:
            total += (emoji_size + 2) * len(val)
    return total


async def create_welcome_image(user, chat) -> BytesIO:
    """
    Create anime-style welcome image with user profile photo.
    Supports Unicode bold group names and color emojis.
    """
    W, H = 800, 400

    # Anime gradient background
    bg = Image.new("RGBA", (W, H), (10, 10, 30, 255))
    draw = ImageDraw.Draw(bg)

    for y in range(H):
        r = int(10 + (y / H) * 20)
        g = int(10 + (y / H) * 5)
        b = int(30 + (y / H) * 40)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Anime border lines
    for i in range(3):
        draw.line([(0, 5 + i * 4), (W, 5 + i * 4)], fill=(100, 50, 200), width=1)
        draw.line([(0, H - 5 - i * 4), (W, H - 5 - i * 4)], fill=(100, 50, 200), width=1)

    # Glowing circle behind avatar
    cx, cy, radius = 160, 200, 115
    for offset in range(20, 0, -1):
        glow_color = (130, 80, 255)
        draw.ellipse(
            [cx - radius - offset, cy - radius - offset,
             cx + radius + offset, cy + radius + offset],
            outline=glow_color,
        )

    # Fetch and paste user profile photo
    pfp_image = None
    try:
        async for photo in app.get_chat_photos(user.id, limit=1):
            photo_file = await app.download_media(photo, in_memory=True)
            pfp_image = Image.open(photo_file).convert("RGBA").resize((220, 220))
            break
    except Exception:
        pass

    if pfp_image:
        mask = Image.new("L", (220, 220), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([0, 0, 220, 220], fill=255)
        pfp_image.putalpha(mask)
        bg.paste(pfp_image, (cx - 110, cy - 110), pfp_image)
    else:
        draw.ellipse([cx - 90, cy - 90, cx + 90, cy + 90], fill=(60, 40, 120))

    # Avatar border ring
    draw.ellipse([cx - 112, cy - 112, cx + 112, cy + 112], outline=(180, 100, 255), width=3)
    draw.ellipse([cx - 116, cy - 116, cx + 116, cy + 116], outline=(100, 50, 200), width=1)

    # Load fonts
    try:
        font_big = ImageFont.truetype(FONT_BOLD, 36)
        font_med = ImageFont.truetype(FONT_REGULAR, 22)
        font_small = ImageFont.truetype(FONT_REGULAR, 17)
    except Exception:
        font_big = ImageFont.load_default()
        font_med = font_big
        font_small = font_big

    text_x = 310

    # "WELCOME" heading
    draw.text((text_x, 90), "✦ WELCOME ✦", fill=(200, 150, 255), font=font_big)

    # User name
    name = user.first_name or "User"
    if len(name) > 18:
        name = name[:17] + "…"
    draw.text((text_x, 145), name, fill=(255, 255, 255), font=font_big)

    # Divider
    draw.line([(text_x, 200), (760, 200)], fill=(130, 80, 255), width=2)

    # Group name — with full Unicode + emoji support
    chat_title = chat.title or "Group"
    if len(chat_title) > 28:
        chat_title = chat_title[:27] + "…"
    draw_text_with_emoji(
        bg,
        f"to  {chat_title}",
        (text_x, 215),
        font_med,
        emoji_size=22,
        text_color=(180, 180, 255),
    )

    # Member count
    try:
        count = await app.get_chat_members_count(chat.id)
        draw.text((text_x, 255), f"👥  Member #{count}", font=font_med, fill=(150, 220, 255))
    except Exception:
        pass

    # Bottom tag
    draw.text((text_x, 310), "⚡ ʏᴛ ᴠɪʙᴇ ᴍᴜꜱɪᴄ ʙᴏᴛ", fill=(130, 80, 255), font=font_small)
    draw.text((text_x, 335), "🎵 Powered by Yt Vibe Music Bot", fill=(100, 100, 180), font=font_small)

    # Save
    output = BytesIO()
    output.name = "welcome.jpg"
    bg.convert("RGB").save(output, "JPEG", quality=95)
    output.seek(0)
    return output


@app.on_message(filters.new_chat_members & filters.group)
@lang.language()
async def welcome_new_member(_, message: types.Message):
    """
    Welcome new members with anime-style image + profile photo.
    Supports Unicode bold group names and color emojis.
    """
    if message.chat.type != enums.ChatType.SUPERGROUP:
        return

    for member in message.new_chat_members:
        if member.is_bot:
            continue

        try:
            img = await create_welcome_image(member, message.chat)
            name = member.first_name or "User"
            mention = f"<a href='tg://user?id={member.id}'>{name}</a>"

            caption = (
                f"✦ ᴡᴇʟᴄᴏᴍᴇ, {mention}! ✦\n\n"
                f"🌸 ᴛʜᴀɴᴋꜱ ꜰᴏʀ ᴊᴏɪɴɪɴɢ <b>{message.chat.title}</b>\n"
                f"🎵 ᴜꜱᴇ /play ᴛᴏ ꜱᴛᴀʀᴛ ʟɪꜱᴛᴇɴɪɴɢ!\n\n"
                f"•── ⋅ ⋅ ──⋅᯽⋅── ⋅ ⋅ ──•"
            )

            await message.reply_photo(
                photo=img,
                caption=caption,
                quote=False,
            )

        except Exception:
            # Fallback text only
            try:
                name = member.first_name or "User"
                mention = f"<a href='tg://user?id={member.id}'>{name}</a>"
                await message.reply_text(
                    text=(
                        f"✦ ᴡᴇʟᴄᴏᴍᴇ, {mention}! ✦\n\n"
                        f"🌸 ᴛʜᴀɴᴋꜱ ꜰᴏʀ ᴊᴏɪɴɪɴɢ <b>{message.chat.title}</b>\n"
                        f"🎵 ᴜꜱᴇ /play ᴛᴏ ꜱᴛᴀʀᴛ ʟɪꜱᴛᴇɴɪɴɢ!\n\n"
                        f"•── ⋅ ⋅ ──⋅᯽⋅── ⋅ ⋅ ──•"
                    ),
                    quote=False,
                )
            except Exception:
                pass
        
