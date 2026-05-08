# Elevenyts/plugins/features/tagall.py
# /all, .all, @all - Tag all members in group
# Only admins can use this

import asyncio
from pyrogram import filters
from pyrogram.types import Message
from pyrogram.errors import ChatAdminRequired, FloodWait
from pyrogram.enums import ChatMemberStatus

from Elevenyts import app


async def _is_admin(client, chat_id: int, user_id: int) -> bool:
    """Check if user is admin — handles all edge cases"""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )
    except Exception as e:
        # If error fetching — deny by default
        print(f"[AdminCheck Error] {e}")
        return False


@app.on_message(
    (
        filters.command(["all"], prefixes=["/", ".", "@"]) |
        filters.regex(r"^@all(\s+.*)?$")
    ) & filters.group
)
async def tag_all_members(client, message: Message):
    chat_id = message.chat.id

    # ✅ FIX 1: Anonymous admin check (from_user is None)
    if not message.from_user:
        # Anonymous admin — allow them
        user_id = None
        is_anon_admin = True
    else:
        user_id = message.from_user.id
        is_anon_admin = False

    # ✅ FIX 2: Skip admin check for anonymous admins
    if not is_anon_admin:
        admin_status = await _is_admin(client, chat_id, user_id)
        if not admin_status:
            return await message.reply_text(
                "❌ Only **Admins** can use this command!"
            )

    # Extract custom message
    text = message.text or ""
    custom_msg = ""

    if text.lower().startswith("@all"):
        parts = text.split(None, 1)
        custom_msg = parts[1].strip() if len(parts) > 1 else ""
    elif message.command and len(message.command) > 1:
        custom_msg = message.text.split(None, 1)[1].strip()

    status = await message.reply_text("⏳ Tagging all members, please wait...")

    mentions = []
    total_tagged = 0

    try:
        async for member in client.get_chat_members(chat_id):
            user = member.user
            if user.is_bot or user.is_deleted:
                continue

            name = user.first_name or "User"
            mentions.append(f"[{name}](tg://user?id={user.id})")
            total_tagged += 1

            if len(mentions) == 20:
                try:
                    await message.reply_text(
                        " ".join(mentions),
                        disable_web_page_preview=True,
                    )
                except FloodWait as fw:
                    await asyncio.sleep(fw.value + 1)
                    await message.reply_text(
                        " ".join(mentions),
                        disable_web_page_preview=True,
                    )
                mentions.clear()
                await asyncio.sleep(0.5)

        # Send remaining
        if mentions:
            try:
                await message.reply_text(
                    " ".join(mentions),
                    disable_web_page_preview=True,
                )
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 1)
                await message.reply_text(
                    " ".join(mentions),
                    disable_web_page_preview=True,
                )

        # Custom announcement
        if custom_msg:
            await message.reply_text(f"📢 **Announcement:**\n{custom_msg}")

        await status.edit_text(
            f"✅ Successfully tagged **{total_tagged}** members!"
        )

    except ChatAdminRequired:
        await status.edit_text(
            "❌ Make the bot an **Admin** in this group to fetch members list!"
        )
    except FloodWait as fw:
        await status.edit_text(
            f"⚠️ Flood wait! Try again after **{fw.value} seconds**."
        )
    except Exception as e:
        await status.edit_text(f"❌ Error: `{e}`")
