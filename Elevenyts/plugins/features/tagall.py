# Elevenyts/plugins/features/tagall.py
# /all, .all, @all - Tag all members in group
# Only admins can use this

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.errors import ChatAdminRequired, FloodWait
from pyrogram.enums import ChatMemberStatus

import asyncio
from Elevenyts import app


async def _is_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )
    except Exception:
        return False


@app.on_message(
    (
        filters.command(["all"], prefixes=["/", ".", "@"]) |
        filters.regex(r"^@all(\s+.*)?$")
    ) & filters.group
)
async def tag_all_members(client, message: Message):
    chat_id = message.chat.id

    # Safety check: make sure message is from a real user
    if not message.from_user:
        return

    user_id = message.from_user.id

    # Admin check
    if not await _is_admin(client, chat_id, user_id):
        return await message.reply_text(
            "❌ Only **Admins** can use this command!"
        )

    # Extract custom message from /all or @all
    text = message.text or ""
    custom_msg = ""

    if text.lower().startswith("@all"):
        parts = text.split(None, 1)
        custom_msg = parts[1].strip() if len(parts) > 1 else ""
    elif message.command:
        custom_msg = message.text.split(None, 1)[1].strip() if len(message.command) > 1 else ""

    status = await message.reply_text("⏳ Tagging all members, please wait...")

    mentions = []
    total_tagged = 0

    try:
        async for member in client.get_chat_members(chat_id):
            user = member.user

            # Skip bots and deleted accounts
            if user.is_bot or user.is_deleted:
                continue

            name = user.first_name or "User"
            mentions.append(f"[{name}](tg://user?id={user.id})")
            total_tagged += 1

            # Send every 20 members to avoid flood
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
                await asyncio.sleep(0.5)  # Small delay between batches

        # Send remaining members
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

        # Send custom message if provided
        if custom_msg:
            await message.reply_text(f"📢 **Announcement:**\n{custom_msg}")

        # Update status with summary
        await status.edit_text(
            f"✅ Successfully tagged **{total_tagged}** members!"
        )

    except ChatAdminRequired:
        await status.edit_text(
            "❌ Please make the bot an **Admin** in this group to fetch members list!"
        )
    except FloodWait as fw:
        await status.edit_text(
            f"⚠️ Flood wait triggered. Please try again after **{fw.value} seconds**."
        )
    except Exception as e:
        await status.edit_text(f"❌ Error occurred: `{e}`")
