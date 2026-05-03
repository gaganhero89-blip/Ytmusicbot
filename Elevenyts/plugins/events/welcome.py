import asyncio
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pyrogram import enums, filters, types

from Elevenyts import app, config, db, lang


async def create_welcome_image(user, chat) -> BytesIO:
    """
    Create anime-style welcome image with user profile photo.
    Returns BytesIO image object.
    """
    # Canvas size
    W, H = 800, 400

    # Anime gradient background (dark blue-purple)
    bg = Image.new("RGB", (W, H), (10, 10, 30))
    draw = ImageDraw.Draw(bg)

    # Draw anime-style gradient overlay
    for y in range(H):
        r = int(10 + (y / H) * 20)
        g = int(10 + (y / H) * 5)
        b = int(30 + (y / H) * 40)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Draw decorative anime lines (top & bottom border)
    for i in range(3):
        draw.line([(0, 5 + i * 4), (W, 5 + i * 4)], fill=(100, 50, 200), width=1)
        draw.line([(0, H - 5 - i * 4), (W, H - 5 - i * 4)], fill=(100, 50, 200), width=1)

    # Draw glowing circle behind avatar
    cx, cy, r = 160, 200, 115
    for offset in range(20, 0, -1):
        alpha = int(255 * (offset / 20) * 0.3)
        draw.ellipse(
            [cx - r - offset, cy - r - offset, cx + r + offset, cy + r + offset],
            outline=(130, 80, 255, alpha),
        )

    # Fetch user profile photo
    pfp_image = None
    try:
        async for photo in app.get_chat_photos(user.id, limit=1):
            photo_file = await app.download_media(photo, in_memory=True)
            pfp_image = Image.open(photo_file).convert("RGBA").resize((220, 220))
            break
    except Exception:
        pass

    if pfp_image:
        # Circular crop for pfp
        mask = Image.new("L", (220, 220), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([0, 0, 220, 220], fill=255)
        pfp_image.putalpha(mask)
        bg.paste(pfp_image, (cx - 110, cy - 110), pfp_image)
    else:
        # Default circle if no photo
        draw.ellipse([cx - 90, cy - 90, cx + 90, cy + 90], fill=(60, 40, 120))
        draw.text((cx, cy), "?", fill=(200, 200, 255), anchor="mm")

    # Anime border ring around pfp
    draw.ellipse([cx - 112, cy - 112, cx + 112, cy + 112], outline=(180, 100, 255), width=3)
    draw.ellipse([cx - 116, cy - 116, cx + 116, cy + 116], outline=(100, 50, 200), width=1)

    # Text area
    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
    except Exception:
        font_big = ImageFont.load_default()
        font_med = font_big
        font_small = font_big

    text_x = 310

    # "WELCOME" heading in anime style
    draw.text((text_x, 90), "✦ WELCOME ✦", fill=(200, 150, 255), font=font_big)

    # User name
    name = user.first_name or "User"
    if len(name) > 18:
        name = name[:17] + "…"
    draw.text((text_x, 145), name, fill=(255, 255, 255), font=font_big)

    # Divider line
    draw.line([(text_x, 200), (760, 200)], fill=(130, 80, 255), width=2)

    # Group name
    chat_title = chat.title or "Group"
    if len(chat_title) > 24:
        chat_title = chat_title[:23] + "…"
    draw.text((text_x, 215), f"to  {chat_title}", fill=(180, 180, 255), font=font_med)

    # Member count
    try:
        count = await app.get_chat_members_count(chat.id)
        draw.text((text_x, 255), f"👥  Member #{count}", fill=(150, 220, 255), font=font_med)
    except Exception:
        pass

    # Bottom anime tag
    draw.text((text_x, 310), "⚡ ᴀᴅᴀᴍ ᴍᴜꜱɪᴄ", fill=(130, 80, 255), font=font_small)
    draw.text((text_x, 335), "🎵 Powered by Adam", fill=(100, 100, 180), font=font_small)

    # Save to BytesIO
    output = BytesIO()
    output.name = "welcome.jpg"
    bg.convert("RGB").save(output, "JPEG", quality=95)
    output.seek(0)
    return output


@app.on_message(filters.new_chat_members & filters.group)
@lang.language()
async def welcome_new_member(_, message: types.Message):
    """
    Welcome new members with anime-style image + their profile photo.
    Only works in supergroups.
    """
    if message.chat.type != enums.ChatType.SUPERGROUP:
        return

    for member in message.new_chat_members:
        # Skip bots
        if member.is_bot:
            continue

        try:
            # Generate anime welcome image
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

        except Exception as e:
            # Fallback: text only
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
                
