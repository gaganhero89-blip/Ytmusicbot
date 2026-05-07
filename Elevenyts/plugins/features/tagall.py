# Elevenyts/plugins/features/tagall.py
# /all, .all, @all - Tag all members in group
# Only admins can use this

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.errors import ChatAdminRequired

from Elevenyts import app


async def _is_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
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
    user_id = message.from_user.id

    # Admin check
    if not await _is_admin(client, chat_id, user_id):
        return await message.reply_text(
            "❌ Yeh command sirf **Admins** use kar sakte hain!"
        )

    # /all ya @all dono se custom message extract karo
    text = message.text or ""
    if text.startswith("@all"):
        parts = text.split(None, 1)
        custom_msg = parts[1] if len(parts) > 1 else ""
    else:
        custom_msg = message.text.split(None, 1)[1] if len(message.command) > 1 else ""

    status = await message.reply_text("⏳ Sabko tag kar raha hoon...")

    mentions = []
    try:
        async for member in client.get_chat_members(chat_id):
            user = member.user
            if user.is_bot or user.is_deleted:
                continue

            name = user.first_name or "User"
            mentions.append(f"[{name}](tg://user?id={user.id})")

            # Har 20 members pe ek message bhejo (flood avoid)
            if len(mentions) == 20:
                await message.reply_text(
                    " ".join(mentions),
                    disable_web_page_preview=True,
                )
                mentions.clear()

        # Bache hue members
        if mentions:
            await message.reply_text(
                " ".join(mentions),
                disable_web_page_preview=True,
            )

        # Custom message agar likha ho
        if custom_msg:
            await message.reply_text(f"📢 {custom_msg}")

        await status.delete()

    except ChatAdminRequired:
        await status.edit_text(
            "❌ Bot ko group mein **Admin** banao, tabhi members list milegi!"
        )
    except Exception as e:
        await status.edit_text(f"❌ Error: `{e}`")
