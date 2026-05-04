import asyncio
import logging
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import AccessTokenInvalid

from Elevenyts import app, userbot
from Elevenyts.utils.database import db
import config

# ─────────────────────────────────────────
#         DATABASE FUNCTIONS
# ─────────────────────────────────────────

async def save_clone(user_id: int, data: dict):
    await db.clones.update_one(
        {"user_id": user_id},
        {"$set": data},
        upsert=True
    )

async def get_clone(user_id: int):
    return await db.clones.find_one({"user_id": user_id})

async def delete_clone(user_id: int):
    await db.clones.delete_one({"user_id": user_id})

async def get_all_clones():
    return await db.clones.find({}).to_list(length=None)


# ─────────────────────────────────────────
#         RUNNING CLONES STORE
# ─────────────────────────────────────────

running_clones = {}  # user_id: {"bot_client": Client, "assistant": Client or None}


# ─────────────────────────────────────────
#         START CLONE CLIENT
# ─────────────────────────────────────────

async def start_clone_client(clone_data: dict):
    user_id = clone_data["user_id"]
    bot_token = clone_data["bot_token"]
    string_session = clone_data.get("string_session")

    try:
        # Clone bot client
        clone_client = Client(
            name=f"clone_{user_id}",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=bot_token,
            in_memory=True,
        )

        # Assistant — apna ya main bot ka
        if string_session:
            assistant_client = Client(
                name=f"clone_asst_{user_id}",
                api_id=config.API_ID,
                api_hash=config.API_HASH,
                session_string=string_session,
                in_memory=True,
            )
            await assistant_client.start()
        else:
            assistant_client = None  # Main bot ka userbot use hoga

        await clone_client.start()
        bot_info = await clone_client.get_me()

        # Customization values
        start_img = clone_data.get("start_img") or config.START_IMG_URL
        support_channel = clone_data.get("support_channel") or config.SUPPORT_CHANNEL
        support_chat = clone_data.get("support_chat") or config.SUPPORT_CHAT

        # ── /start Handler ──
        @clone_client.on_message(filters.command("start") & filters.private)
        async def clone_start_cmd(client, message: Message):
            await message.reply_photo(
                photo=start_img,
                caption=(
                    f"🎵 **Hello {message.from_user.mention}!**\n\n"
                    f"Main ek Music Bot hoon!\n"
                    f"Group mein add karo aur /play se gaana sunao 🎶\n\n"
                    f"📢 {support_channel}\n"
                    f"💬 {support_chat}"
                ),
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("📢 Channel", url=support_channel),
                        InlineKeyboardButton("💬 Support", url=support_chat),
                    ]
                ])
            )

        # ── /help Handler ──
        @clone_client.on_message(filters.command("help"))
        async def clone_help_cmd(client, message: Message):
            await message.reply_text(
                "🎵 **Music Bot Commands:**\n\n"
                "▶️ `/play [song/link]` — Song play karo\n"
                "🎥 `/vplay [song/link]` — Video play karo\n"
                "⏹ `/stop` — Music band karo\n"
                "⏸ `/pause` — Pause karo\n"
                "▶️ `/resume` — Resume karo\n"
                "⏭ `/skip` — Next song\n"
                "🔊 `/volume [1-200]` — Volume\n"
                "📋 `/queue` — Queue dekho\n"
                "🏓 `/ping` — Bot check karo\n\n"
                f"📢 Channel: {support_channel}\n"
                f"💬 Support: {support_chat}"
            )

        # ── /ping Handler ──
        @clone_client.on_message(filters.command("ping"))
        async def clone_ping_cmd(client, message: Message):
            await message.reply_text("🏓 **Pong!** Bot alive hai ✅")

        # ── Music Commands → Main bot ke through ──
        @clone_client.on_message(
            filters.command([
                "play", "vplay", "cplay", "stop", "pause", "resume",
                "skip", "queue", "volume", "end", "shuffle", "loop",
                "seek", "next", "reload", "radio"
            ]) & filters.group
        )
        async def clone_music_cmd(client, message: Message):
            chat_id = message.chat.id
            cmd = message.command[0]
            args = " ".join(message.command[1:]) if len(message.command) > 1 else ""
            full_cmd = f"/{cmd} {args}".strip()

            try:
                main_bot_info = await app.get_me()
                # Check karo main bot group mein hai ya nahi
                try:
                    await app.get_chat_member(chat_id, main_bot_info.id)
                except Exception:
                    await message.reply_text(
                        f"⚠️ **Pehle Main Bot ko group mein add karo!**\n\n"
                        f"👉 @{main_bot_info.username} ko **admin** banao, phir dobara try karo."
                    )
                    return

                await app.send_message(chat_id, full_cmd)

            except Exception as e:
                await message.reply_text(f"❌ Error: `{e}`")

        running_clones[user_id] = {
            "bot_client": clone_client,
            "assistant": assistant_client,
            "bot_info": bot_info,
        }

        logging.info(f"[CLONE] Started: @{bot_info.username} (user: {user_id})")
        return True, bot_info.username

    except AccessTokenInvalid:
        return False, "invalid_token"
    except Exception as e:
        logging.error(f"[CLONE] Start error: {e}")
        return False, str(e)


async def stop_clone_client(user_id: int):
    if user_id in running_clones:
        try:
            data = running_clones[user_id]
            await data["bot_client"].stop()
            if data.get("assistant"):
                await data["assistant"].stop()
            del running_clones[user_id]
        except Exception as e:
            logging.error(f"[CLONE] Stop error: {e}")


# ─────────────────────────────────────────
#         AUTO START ALL CLONES ON BOOT
# ─────────────────────────────────────────

async def start_all_clones():
    await asyncio.sleep(5)  # Main bot ke start hone ka wait karo
    clones = await get_all_clones()
    started = 0
    for clone in clones:
        if clone.get("active"):
            success, _ = await start_clone_client(clone)
            if success:
                started += 1
    logging.info(f"[CLONE] Auto-started {started}/{len(clones)} clones.")

asyncio.get_event_loop().create_task(start_all_clones())


# ─────────────────────────────────────────
#         CONVERSATION SESSIONS
# ─────────────────────────────────────────

clone_sessions = {}

STEPS = ["bot_token", "owner_id", "string_session", "start_img", "support_channel", "support_chat"]

STEP_MESSAGES = {
    "bot_token": (
        "🤖 **Step 1/6 — Bot Token**\n\n"
        "Apne clone bot ka **Bot Token** bhejo.\n"
        "👉 @BotFather → /newbot → token copy karo\n\n"
        "`/cancel` — band karne ke liye"
    ),
    "owner_id": (
        "👤 **Step 2/6 — Owner ID**\n\n"
        "Apni **Telegram User ID** bhejo.\n"
        "👉 ID nahi pata? @userinfobot use karo\n\n"
        "`/cancel` — band karne ke liye"
    ),
    "string_session": (
        "🔑 **Step 3/6 — String Session (Optional)**\n\n"
        "Apna **assistant account** add karna chahte ho?\n\n"
        "✅ **Haan** → String Session bhejo\n"
        "⏭ **Nahi** → `/skip` bhejo (Main bot ka assistant use hoga)\n\n"
        "💡 String Session banao: @StringSessionBot\n\n"
        "`/cancel` — band karne ke liye"
    ),
    "start_img": (
        "🖼 **Step 4/6 — Start Image URL**\n\n"
        "Clone bot ki **start image URL** bhejo.\n"
        "Ya `/skip` bhejo (default image use hogi)\n\n"
        "`/cancel` — band karne ke liye"
    ),
    "support_channel": (
        "📢 **Step 5/6 — Support Channel**\n\n"
        "Apne channel ka link bhejo.\n"
        "Example: `https://t.me/yourchannel`\n"
        "Ya `/skip` bhejo\n\n"
        "`/cancel` — band karne ke liye"
    ),
    "support_chat": (
        "💬 **Step 6/6 — Support Chat**\n\n"
        "Apne group ka link bhejo.\n"
        "Example: `https://t.me/yourchat`\n"
        "Ya `/skip` bhejo\n\n"
        "`/cancel` — band karne ke liye"
    ),
}


# ─────────────────────────────────────────
#         /clone COMMAND
# ─────────────────────────────────────────

@app.on_message(filters.command("clone") & filters.private)
async def clone_start(_, message: Message):
    user_id = message.from_user.id
    existing = await get_clone(user_id)

    if existing:
        is_running = user_id in running_clones
        await message.reply_text(
            f"⚠️ **Tumhara clone bot pehle se exist karta hai!**\n\n"
            f"🤖 Bot: @{existing.get('bot_username', 'N/A')}\n"
            f"🔑 Assistant: {'Apna' if existing.get('string_session') else 'Main Bot ka'}\n"
            f"📶 Status: {'🟢 Online' if is_running else '🔴 Offline'}\n\n"
            "Naya banane ke liye pehle /deleteclone karo.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Delete Clone", callback_data="confirm_delete_clone")],
                [InlineKeyboardButton("🔄 Restart Clone", callback_data="restart_clone")],
            ])
        )
        return

    clone_sessions[user_id] = {"step": 0, "data": {}}
    await message.reply_text(
        "🎉 **Clone Bot Setup!**\n\n"
        "Tumhara khud ka music bot banega.\n"
        "Sab features same — main bot ka database use hoga.\n\n"
        "Shuru karte hain! 👇"
    )
    await asyncio.sleep(1)
    await message.reply_text(STEP_MESSAGES["bot_token"])


# ─────────────────────────────────────────
#         STEP HANDLER
# ─────────────────────────────────────────

@app.on_message(
    filters.private & filters.text &
    ~filters.command(["start", "help", "clone", "deleteclone", "myclone"])
)
async def clone_step_handler(_, message: Message):
    user_id = message.from_user.id
    if user_id not in clone_sessions:
        return

    session = clone_sessions[user_id]
    step_index = session["step"]
    text = message.text.strip()
    skippable = ["string_session", "start_img", "support_channel", "support_chat"]
    current_step = STEPS[step_index]

    if text == "/cancel":
        del clone_sessions[user_id]
        await message.reply_text("❌ Clone process cancel ho gaya.")
        return

    if text == "/skip" and current_step in skippable:
        session["data"][current_step] = None
    else:
        if current_step == "bot_token":
            if ":" not in text or len(text) < 30:
                await message.reply_text("❌ Invalid Bot Token! Dobara bhejo.")
                return
            session["data"]["bot_token"] = text

        elif current_step == "owner_id":
            if not text.isdigit():
                await message.reply_text("❌ Sirf numbers mein Owner ID bhejo!")
                return
            session["data"]["owner_id"] = int(text)

        elif current_step == "string_session":
            if len(text) < 50:
                await message.reply_text("❌ Invalid String Session! Ya /skip karo.")
                return
            session["data"]["string_session"] = text

        elif current_step == "start_img":
            if not text.startswith("http"):
                await message.reply_text("❌ Valid URL bhejo. Ya /skip karo.")
                return
            session["data"]["start_img"] = text

        elif current_step in ["support_channel", "support_chat"]:
            if not text.startswith("https://t.me/"):
                await message.reply_text("❌ Valid t.me link bhejo. Ya /skip karo.")
                return
            session["data"][current_step] = text

    session["step"] += 1

    if session["step"] < len(STEPS):
        await message.reply_text(STEP_MESSAGES[STEPS[session["step"]]])
    else:
        await finish_clone(message, user_id, session["data"])
        del clone_sessions[user_id]


# ─────────────────────────────────────────
#         FINISH CLONE
# ─────────────────────────────────────────

async def finish_clone(message: Message, user_id: int, data: dict):
    processing = await message.reply_text("⏳ **Setup ho raha hai... wait karo!**")

    success, result = await start_clone_client({"user_id": user_id, **data})

    if not success:
        err = "Invalid Bot Token!" if result == "invalid_token" else f"Error: `{result}`"
        await processing.edit_text(f"❌ **{err}**\n\nDobara /clone karo.")
        return

    bot_username = result
    clone_data = {
        "user_id": user_id,
        "bot_token": data["bot_token"],
        "owner_id": data["owner_id"],
        "bot_username": bot_username,
        "string_session": data.get("string_session"),
        "start_img": data.get("start_img"),
        "support_channel": data.get("support_channel"),
        "support_chat": data.get("support_chat"),
        "active": True,
    }
    await save_clone(user_id, clone_data)

    asst = "✅ Apna Assistant" if data.get("string_session") else "🔄 Main Bot ka Assistant"

    await processing.edit_text(
        f"✅ **Clone Bot Live Ho Gaya!**\n\n"
        f"🤖 **Bot:** @{bot_username}\n"
        f"👤 **Owner ID:** `{data['owner_id']}`\n"
        f"🔑 **Assistant:** {asst}\n"
        f"🖼 **Image:** {'Custom ✅' if data.get('start_img') else 'Default'}\n"
        f"📢 **Channel:** {'Custom ✅' if data.get('support_channel') else 'Default'}\n"
        f"💬 **Chat:** {'Custom ✅' if data.get('support_chat') else 'Default'}\n\n"
        f"📌 **@{bot_username} ko group mein add karo!**\n"
        f"⚠️ **Main bot bhi group mein admin hona chahiye music ke liye!**\n\n"
        f"🗑 Hatane ke liye: /deleteclone",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🤖 @{bot_username}", url=f"https://t.me/{bot_username}")]
        ])
    )


# ─────────────────────────────────────────
#         /myclone
# ─────────────────────────────────────────

@app.on_message(filters.command("myclone") & filters.private)
async def my_clone(_, message: Message):
    user_id = message.from_user.id
    clone = await get_clone(user_id)
    if not clone:
        await message.reply_text("❌ Tumhara koi clone nahi hai.\n\n/clone karo!")
        return

    is_running = user_id in running_clones
    asst = "Apna" if clone.get("string_session") else "Main Bot ka"

    await message.reply_text(
        f"🤖 **Tumhara Clone:**\n\n"
        f"**Bot:** @{clone.get('bot_username', 'N/A')}\n"
        f"**Owner ID:** `{clone.get('owner_id', 'N/A')}`\n"
        f"**Assistant:** {asst}\n"
        f"**Status:** {'🟢 Online' if is_running else '🔴 Offline'}\n",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 Open Bot", url=f"https://t.me/{clone.get('bot_username', 'me')}")],
            [InlineKeyboardButton("🔄 Restart", callback_data="restart_clone")],
            [InlineKeyboardButton("🗑 Delete", callback_data="confirm_delete_clone")],
        ])
    )


# ─────────────────────────────────────────
#         /deleteclone
# ─────────────────────────────────────────

@app.on_message(filters.command("deleteclone") & filters.private)
async def delete_clone_cmd(_, message: Message):
    user_id = message.from_user.id
    clone = await get_clone(user_id)
    if not clone:
        await message.reply_text("❌ Tumhara koi clone nahi hai!")
        return

    await message.reply_text(
        f"⚠️ **@{clone.get('bot_username')} delete karna chahte ho?**",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Haan", callback_data="confirm_delete_clone"),
                InlineKeyboardButton("❌ Nahi", callback_data="cancel_delete_clone"),
            ]
        ])
    )


# ─────────────────────────────────────────
#         CALLBACKS
# ─────────────────────────────────────────

@app.on_callback_query(filters.regex("confirm_delete_clone"))
async def confirm_delete(_, cb):
    user_id = cb.from_user.id
    await stop_clone_client(user_id)
    await delete_clone(user_id)
    await cb.message.edit_text(
        "✅ **Clone delete ho gaya!**\n\nNaya banane ke liye /clone karo."
    )


@app.on_callback_query(filters.regex("cancel_delete_clone"))
async def cancel_delete(_, cb):
    await cb.message.edit_text("❌ Delete cancel. Clone abhi bhi active hai! ✅")


@app.on_callback_query(filters.regex("restart_clone"))
async def restart_clone_cb(_, cb):
    user_id = cb.from_user.id
    clone = await get_clone(user_id)
    if not clone:
        await cb.answer("❌ Clone nahi mila!", show_alert=True)
        return
    await cb.answer("🔄 Restart ho raha hai...")
    await stop_clone_client(user_id)
    success, result = await start_clone_client(clone)
    if success:
        await cb.message.edit_text(
            f"✅ **Clone restart ho gaya!**\n🤖 @{result} online hai!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Open", url=f"https://t.me/{result}")]
            ])
        )
    else:
        await cb.message.edit_text(f"❌ Restart fail: `{result}`")
      
