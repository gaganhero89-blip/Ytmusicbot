from pyrogram import filters
from pyrogram import Client as ElevenYts
from pyrogram.types import Message
from pyrogram.errors import ChatAdminRequired, UserNotParticipant, FloodWait
import asyncio

# ==============================
# TAG ALL MEMBERS PLUGIN
# For: ElevenYts / Ytmusicbot
# Command: /all or @all
# ==============================

CHUNK_SIZE = 5  # mentions per message (avoids flood)


@ElevenYts.on_message(filters.command(["all", "tagall"]) & filters.group)
async def tag_all_members(client, message: Message):
    chat_id = message.chat.id

    # Optional custom message after command
    custom_msg = ""
    if len(message.command) > 1:
        custom_msg = message.text.split(None, 1)[1]

    header = f"📢 **Tag All**\n{custom_msg}\n\n" if custom_msg else "📢 **Tag All Members!**\n\n"

    try:
        members = []
        async for member in client.get_chat_members(chat_id):
            # Skip bots and deleted accounts
            if member.user.is_bot or member.user.is_deleted:
                continue
            members.append(member.user)

        if not members:
            await message.reply_text("❌ No members found to tag.")
            return

        # Split into chunks and send
        for i in range(0, len(members), CHUNK_SIZE):
            chunk = members[i:i + CHUNK_SIZE]
            mention_text = header if i == 0 else ""
            for user in chunk:
                name = user.first_name or "User"
                mention_text += f"[{name}](tg://user?id={user.id}) "
            await message.reply_text(
                mention_text,
                disable_web_page_preview=True
            )
            await asyncio.sleep(1.5)  # avoid flood wait

    except ChatAdminRequired:
        await message.reply_text("❌ I need admin rights to get member list!")
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as ex:
        await message.reply_text(f"❌ Error: {ex}")


@ElevenYts.on_message(filters.regex(r"^@all$") & filters.group)
async def tag_all_via_mention(client, message: Message):
    """Trigger tag all when someone sends @all in group"""
    await tag_all_members(client, message)
