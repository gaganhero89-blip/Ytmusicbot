# Elevenyts/plugins/features/tagall.py
# Tag All Members Feature - /all command
# Made for Ytmusicbot by gaganhero89-blip

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.errors import ChatAdminRequired

from Elevenyts import app


# ── Helper: check if user is admin ──────────────────────────
async def is_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


# ── Main Command Handler ─────────────────────────────────────
@app.on_message(
    filters.command(["all"], prefixes=["/", ".", "@"]) & filters.group
)
async def tag_all_members(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Sirf admin use kar sake
    if not await is_admin(client, chat_id, user_id):
        return await message.reply_text(
            "❌ **Sirf Admins** yeh command use kar sakte hain!"
        )

    # Optional custom message
    custom_msg = ""
    if len(message.command) > 1:
        custom_msg = message.text.split(None, 1)[1]

    wait_msg = await message.reply_text("⏳ Tagging all members...")

    mentions = []

    try:
        async for member in client.get_chat_members(chat_id):
            user = member.user
            # Bots aur deleted accounts skip karo
            if user.is_bot or user.is_deleted:
                continue

            name = user.first_name or "User"
            mentions.append(f"[{name}](tg://user?id={user.id})")

            # 20 per message batch (Telegram flood limit se bachne ke liye)
            if len(mentions) == 20:
                await message.reply_text(
                    " ".join(mentions),
                    disable_web_page_preview=True,
                )
                mentions.clear()

        # Remaining mentions
        if mentions:
            await message.reply_text(
                " ".join(mentions),
                disable_web_page_preview=True,
            )

        # Custom message agar diya
        if custom_msg:
            await message.reply_text(f"📢 {custom_msg}")

        await wait_msg.delete()

    except ChatAdminRequired:
        await wait_msg.edit_text(
            "❌ Bot ko **Admin** banana padega members list dekhne ke liye!"
        )
    except Exception as e:
        await wait_msg.edit_text(f"❌ Error aaya: `{e}`")
