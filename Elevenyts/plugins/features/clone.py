"""
Clone System — Yt Vibe Music Bot (Pro Level)
Full music support with proper assistant handling.
checkUB logic built-in using clone's own client.
"""

import asyncio
from datetime import datetime

from pyrogram import Client, enums, errors, filters, types
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pytgcalls import PyTgCalls

from Elevenyts import app, config, db, lang
from Elevenyts.core.calls import Anony

# ── Collections ───────────────────────────────────────────────
CLONE_COL    = "clones"
PLAYLIST_COL = "playlists"
PREMIUM_COL  = "clone_premium"

# ── Running clones ─────────────────────────────────────────────
running_clones: dict[int, dict] = {}


# ══════════════════════════════════════════════════════════════
# DB HELPERS
# ══════════════════════════════════════════════════════════════

async def get_clone(user_id: int) -> dict | None:
    return await db.db[CLONE_COL].find_one({"user_id": user_id})

async def save_clone(data: dict):
    await db.db[CLONE_COL].update_one(
        {"user_id": data["user_id"]}, {"$set": data}, upsert=True
    )

async def delete_clone_db(user_id: int):
    await db.db[CLONE_COL].delete_one({"user_id": user_id})

async def get_playlist(user_id: int, name: str) -> dict | None:
    return await db.db[PLAYLIST_COL].find_one({"user_id": user_id, "name": name})

async def save_playlist(user_id: int, name: str, songs: list):
    await db.db[PLAYLIST_COL].update_one(
        {"user_id": user_id, "name": name},
        {"$set": {"songs": songs, "updated": datetime.now().strftime("%Y-%m-%d %H:%M")}},
        upsert=True,
    )

async def get_all_playlists(user_id: int) -> list:
    return await db.db[PLAYLIST_COL].find({"user_id": user_id}).to_list(length=20)

async def delete_playlist(user_id: int, name: str):
    await db.db[PLAYLIST_COL].delete_one({"user_id": user_id, "name": name})

async def add_premium_user(owner_id: int, uid: int):
    await db.db[PREMIUM_COL].update_one(
        {"owner_id": owner_id, "user_id": uid},
        {"$set": {"added": datetime.now().strftime("%Y-%m-%d %H:%M")}},
        upsert=True,
    )

async def remove_premium_user(owner_id: int, uid: int):
    await db.db[PREMIUM_COL].delete_one({"owner_id": owner_id, "user_id": uid})


# ══════════════════════════════════════════════════════════════
# KEYBOARDS
# ══════════════════════════════════════════════════════════════

def clone_start_keyboard(clone_data: dict, is_owner: bool = False) -> InlineKeyboardMarkup:
    username = clone_data.get("bot_username", "")
    support  = clone_data.get("support_chat", config.SUPPORT_CHAT)
    channel  = clone_data.get("support_channel", getattr(config, "SUPPORT_CHANNEL", support))
    rows     = []

    if is_owner:
        rows.append([InlineKeyboardButton("👑 ᴏᴡɴᴇʀ ᴘᴀɴᴇʟ", callback_data="cl_owner_panel")])

    rows.append([
        InlineKeyboardButton("➕ ᴀᴅᴅ ᴍᴇ ᴛᴏ ɢʀᴏᴜᴘ 🎵", url=f"https://t.me/{username}?startgroup=true"),
    ])
    rows.append([
        InlineKeyboardButton("💬 ꜱᴜᴘᴘᴏʀᴛ", url=support),
        InlineKeyboardButton("📢 ᴜᴘᴅᴀᴛᴇꜱ",  url=channel),
    ])
    rows.append([
        InlineKeyboardButton("❓ ʜᴇʟᴘ", callback_data="cl_help"),
    ])

    for btn in clone_data.get("extra_buttons", []):
        rows.append([InlineKeyboardButton(btn["text"], url=btn["url"])])

    return InlineKeyboardMarkup(rows)


def owner_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 ꜱᴛᴀᴛꜱ",         callback_data="cl_stats"),
         InlineKeyboardButton("📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ",     callback_data="cl_broadcast")],
        [InlineKeyboardButton("🎨 ᴄᴜꜱᴛᴏᴍɪᴢᴇ",     callback_data="cl_customize"),
         InlineKeyboardButton("👑 ᴘʀᴇᴍɪᴜᴍ",        callback_data="cl_premium_list")],
        [InlineKeyboardButton("🔄 ʀᴇꜱᴛᴀʀᴛ",        callback_data="cl_restart"),
         InlineKeyboardButton("🗑️ ᴅᴇʟᴇᴛᴇ",         callback_data="cl_delete")],
        [InlineKeyboardButton("◀️ ᴄʟᴏꜱᴇ",          callback_data="cl_owner_back")],
    ])


def customize_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📛 ɴᴀᴍᴇ",           callback_data="cust_name"),
         InlineKeyboardButton("🖼 ꜱᴛᴀʀᴛ ɪᴍɢ",     callback_data="cust_startimg")],
        [InlineKeyboardButton("💬 ꜱᴜᴘᴘᴏʀᴛ",        callback_data="cust_support"),
         InlineKeyboardButton("📢 ᴄʜᴀɴɴᴇʟ",        callback_data="cust_channel")],
        [InlineKeyboardButton("👋 ᴡᴇʟᴄᴏᴍᴇ ᴛᴇxᴛ",  callback_data="cust_welcome"),
         InlineKeyboardButton("🔘 ᴇxᴛʀᴀ ʙᴛɴꜱ",    callback_data="cust_buttons")],
        [InlineKeyboardButton("🎵 ᴀꜱꜱɪꜱᴛᴀɴᴛ",     callback_data="cust_assistant"),
         InlineKeyboardButton("👑 ᴘʀᴇᴍɪᴜᴍ",        callback_data="cust_premium")],
        [InlineKeyboardButton("◀️ ʙᴀᴄᴋ",           callback_data="cl_back_panel")],
    ])


# ══════════════════════════════════════════════════════════════
# CLONE UB CHECK — uses clone's own client
# ══════════════════════════════════════════════════════════════

async def clone_check_ub(c: Client, m: types.Message, m_lang: dict) -> bool:
    """
    Proper UB check for clone bot.
    Uses clone's own client (c) — NOT main bot's app.
    Returns True if OK to proceed, False if should abort.
    """
    from Elevenyts import queue, yt

    async def safe_reply(text: str):
        try:
            return await m.reply_text(text)
        except Exception:
            return None

    # Must have from_user
    if not m.from_user:
        await safe_reply(m_lang.get("play_user_invalid", "🔒 Anonymous admin detected!"))
        return False

    # Must be supergroup
    if m.chat.type != enums.ChatType.SUPERGROUP:
        await safe_reply(m_lang.get("play_chat_invalid", "❌ Only works in supergroups."))
        try:
            await c.leave_chat(m.chat.id)
        except Exception:
            pass
        return False

    # Must have query or reply
    if not m.reply_to_message and (
        len(m.command) < 2 or (len(m.command) == 2 and m.command[1] == "-f")
    ):
        await safe_reply(m_lang.get("play_usage", "💡 Usage: /play [song/url]"))
        return False

    # Queue limit check
    if len(queue.get_queue(m.chat.id)) >= config.QUEUE_LIMIT:
        await safe_reply(m_lang.get("play_queue_full", "📋 Queue full!").format(config.QUEUE_LIMIT))
        return False

    # Admin-only play mode check
    force    = m.command[0].endswith("force") or (len(m.command) > 1 and "-f" in m.command[1])
    play_mode = await db.get_play_mode(m.chat.id)
    if play_mode or force:
        adminlist = await db.get_admins(m.chat.id)
        if (
            m.from_user.id not in adminlist
            and not await db.is_auth(m.chat.id, m.from_user.id)
            and m.from_user.id not in app.sudoers
        ):
            await safe_reply(m_lang.get("play_admin", "🛡️ Admin only play."))
            return False

    # Assistant join check — uses clone's client (c)
    if m.chat.id not in db.active_calls:
        assistant = await db.get_client(m.chat.id)
        try:
            member = await c.get_chat_member(m.chat.id, assistant.id)
            if member.status in [enums.ChatMemberStatus.BANNED, enums.ChatMemberStatus.RESTRICTED]:
                try:
                    await c.unban_chat_member(m.chat.id, assistant.id)
                except Exception:
                    await safe_reply(
                        m_lang.get("play_banned", "🚫 Assistant is banned.").format(
                            c.username, assistant.id, assistant.mention,
                            f"@{assistant.username}" if assistant.username else "assistant"
                        )
                    )
                    return False

        except errors.ChatAdminRequired:
            await safe_reply(
                "<blockquote><b>🔐 Bot needs to be Admin!</b>\n\n"
                "Required permissions:\n"
                "• Manage Voice Chats\n"
                "• Invite Users via Link\n"
                "• Delete Messages</blockquote>"
            )
            return False

        except errors.UserNotParticipant:
            # Assistant not in group — try to join using clone client
            try:
                chat = await c.get_chat(m.chat.id)
                if chat.username:
                    invite_link = chat.username
                else:
                    try:
                        invite_link = chat.invite_link
                        if not invite_link:
                            invite_link = await c.export_chat_invite_link(m.chat.id)
                    except errors.ChatAdminRequired:
                        await safe_reply(
                            "<blockquote><b>🔐 Bot needs to be Admin!</b>\n\n"
                            "Please make bot admin with:\n"
                            "• Manage Voice Chats\n"
                            "• Invite Users via Link</blockquote>"
                        )
                        return False

                umm = await safe_reply(
                    m_lang.get("play_invite", "⏳ Inviting assistant...").format(
                        getattr(c, 'username', 'assistant')
                    )
                )
                await asyncio.sleep(1)

                try:
                    await assistant.join_chat(invite_link)
                except errors.UserAlreadyParticipant:
                    pass
                except errors.InviteRequestSent:
                    try:
                        await assistant.approve_chat_join_request(m.chat.id, assistant.id)
                    except Exception as ex:
                        if umm:
                            try:
                                await umm.edit_text(
                                    m_lang.get("play_invite_error", "❌ Failed to invite.").format(
                                        type(ex).__name__
                                    )
                                )
                            except Exception:
                                pass
                        return False
                except Exception as ex:
                    if umm:
                        try:
                            await umm.edit_text(
                                m_lang.get("play_invite_error", "❌ Failed.").format(type(ex).__name__)
                            )
                        except Exception:
                            pass
                    return False

                if umm:
                    try:
                        await umm.delete()
                    except Exception:
                        pass

                try:
                    await assistant.resolve_peer(m.chat.id)
                except Exception:
                    pass

            except Exception as ex:
                await safe_reply(f"❌ Failed to invite assistant: <code>{ex}</code>")
                return False

    return True


# ══════════════════════════════════════════════════════════════
# LAUNCH CLONE
# ══════════════════════════════════════════════════════════════

async def launch_clone(user_id: int, clone_data: dict):
    token             = clone_data["bot_token"]
    bot_name          = clone_data.get("bot_name", "Clone Bot")
    assistant_session = clone_data.get("assistant_session")

    # ── Bot client ───────────────────────────────────────────
    client = Client(
        name=f"clone_{user_id}",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=token,
        in_memory=True,
    )

    # ── Assistant ────────────────────────────────────────────
    assistant = None
    calls     = None
    if assistant_session:
        try:
            assistant = Client(
                name=f"clone_asst_{user_id}",
                api_id=config.API_ID,
                api_hash=config.API_HASH,
                session_string=assistant_session,
                in_memory=True,
            )
            await assistant.start()
            calls = PyTgCalls(assistant)
            await calls.start()
        except Exception as e:
            assistant = None
            calls     = None
            print(f"⚠️ Clone {user_id} assistant failed: {e}")
    if calls is None:
        calls = Anony

    # ══════════════════════════════════════════════════════
    # HANDLERS
    # ══════════════════════════════════════════════════════

    @client.on_message(filters.command("start") & filters.private)
    async def cl_start(c, m: types.Message):
        is_owner = m.from_user.id == user_id
        welcome  = clone_data.get("welcome_text") or (
            f"👋 ʜᴇʟʟᴏ <b>{m.from_user.first_name}</b>!\n\n"
            f"🎵 ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ <b>{bot_name}</b>\n\n"
            f"❤️ ᴜʟᴛʀᴀ ꜱᴍᴏᴏᴛʜ ꜱᴛʀᴇᴀᴍɪɴɢ\n"
            f"⚡ ɪɴꜱᴛᴀɴᴛ ᴘʟᴀʏʙᴀᴄᴋ — ᴢᴇʀᴏ ʟᴀɢ\n"
            f"💖 ᴘʀᴇᴍɪᴜᴍ ꜱᴏᴜɴᴅ ǫᴜᴀʟɪᴛʏ\n\n"
            f"❓ ᴜꜱᴇ /help ꜰᴏʀ ᴄᴏᴍᴍᴀɴᴅꜱ\n\n"
            f"•── ⋅ ⋅ ──⋅᯽⋅── ⋅ ⋅ ──•"
        )
        try:
            await m.reply_photo(
                photo=clone_data.get("start_img", config.START_IMG),
                caption=welcome,
                reply_markup=clone_start_keyboard(clone_data, is_owner=is_owner),
            )
        except Exception:
            await m.reply_text(
                welcome,
                reply_markup=clone_start_keyboard(clone_data, is_owner=is_owner),
            )

    @client.on_message(filters.command("help"))
    async def cl_help_cmd(c, m: types.Message):
        await m.reply_text(
            f"❓ <b>{bot_name} — Commands</b>\n\n"
            f"🎵 <b>Music:</b>\n"
            f"• /play — Play a song\n"
            f"• /vplay — Play video\n"
            f"• /playforce — Force play\n"
            f"• /lyrics — Get lyrics\n"
            f"• /recommend — Song recommendations\n"
            f"• /saveplaylist — Save queue as playlist\n"
            f"• /myplaylists — View saved playlists\n"
            f"• /loadplaylist — Load a playlist\n\n"
            f"⚙️ <b>General:</b>\n"
            f"• /ping — Bot latency\n"
            f"• /start — Start message\n\n"
            f"•── ⋅ ⋅ ──⋅᯽⋅── ⋅ ⋅ ──•"
        )

    @client.on_message(filters.command("ping"))
    async def cl_ping(c, m: types.Message):
        start = datetime.now()
        msg   = await m.reply_text("🏓 ᴘɪɴɢɪɴɢ...")
        ms    = (datetime.now() - start).microseconds // 1000
        await msg.edit_text(
            f"🏓 <b>ᴘᴏɴɢ!</b>\n"
            f"⚡ ʟᴀᴛᴇɴᴄʏ: <code>{ms}ms</code>\n"
            f"🤖 <b>{bot_name}</b> ɪꜱ ᴏɴʟɪɴᴇ ✅"
        )

    # ── /play — FULL PROPER IMPLEMENTATION ──────────────────
    @client.on_message(
        filters.command(["play", "playforce", "vplay", "vplayforce"])
        & filters.group
    )
    async def clone_play(c, m: types.Message):
        from Elevenyts import tune, queue, yt, tg
        from Elevenyts.helpers import buttons as _buttons

        # Get lang
        try:
            from Elevenyts import lang as _lang
            m_lang = await _lang.get_lang(m.chat.id)
        except Exception:
            m_lang = {}

        # ── Run UB check using clone's own client ────────────
        ok = await clone_check_ub(c, m, m_lang)
        if not ok:
            return

        # ── Parse command ────────────────────────────────────
        command = m.command[0].lower()
        video   = "vplay" in command
        force   = "force" in command or (len(m.command) > 1 and "-f" in m.command[1])
        chat_id = m.chat.id
        mention = m.from_user.mention

        play_emoji = m_lang.get("play_emoji", "🎵")

        # ── Delete command message ───────────────────────────
        try:
            await m.delete()
        except Exception:
            pass

        # ── Send searching message ───────────────────────────
        try:
            sent = await m.reply_text(
                m_lang.get("play_searching", "🎵").format(play_emoji)
            )
        except Exception:
            return

        media  = tg.get_media(m.reply_to_message) if m.reply_to_message else None
        tracks = []
        file   = None

        try:
            # Telegram file
            if media:
                setattr(sent, "lang", m_lang)
                file = await tg.download(m.reply_to_message, sent)

            elif len(m.command) >= 2:
                query = " ".join(m.command[1:])
                url   = yt.url(m)

                if url and "playlist" in url:
                    await sent.edit_text(m_lang.get("playlist_fetch", "⏳ Fetching playlist..."))
                    try:
                        tracks = await yt.playlist(config.PLAYLIST_LIMIT, mention, url)
                    except Exception:
                        await sent.edit_text(m_lang.get("playlist_error", "❌ Playlist error."))
                        return
                    if not tracks:
                        await sent.edit_text(m_lang.get("playlist_error", "❌ Playlist error."))
                        return
                    file = tracks[0]
                    tracks.remove(file)
                    file.message_id = sent.id
                else:
                    file = await yt.search(query, sent.id, video=video)
                    if not file:
                        await sent.edit_text(
                            m_lang.get("play_not_found", "❌ Not found.").format(config.SUPPORT_CHAT)
                        )
                        return

            if not file:
                return

            file.video = video
            file.user  = mention

            # Duration check
            if not file.is_live and file.duration_sec > config.DURATION_LIMIT:
                await sent.edit_text(
                    m_lang.get("play_duration_limit", "❌ Too long!").format(config.DURATION_LIMIT // 60)
                )
                return

            # Log
            if await db.is_logger():
                from Elevenyts.helpers import utils as _utils
                await _utils.play_log(m, file.title, file.duration)

            # Queue
            if force:
                queue.force_add(chat_id, file)
            else:
                position = queue.add(chat_id, file)
                if await db.get_call(chat_id):
                    await sent.edit_text(
                        m_lang.get("play_queued", "✅ #{0}\n🎵 {2}\n⏱ {3}\n👤 {4}").format(
                            position, file.url, file.title, file.duration, mention
                        ),
                        reply_markup=_buttons.play_queued(
                            chat_id, file.id,
                            m_lang.get("play_now", "▶️ Play Now")
                        ),
                    )
                    if tracks:
                        txt = "<blockquote expandable>"
                        for t in tracks:
                            p    = queue.add(chat_id, t)
                            txt += f"<b>{p}.</b> {t.title}\n"
                        txt = txt[:1948] + "</blockquote>"
                        try:
                            await c.send_message(
                                m.chat.id,
                                m_lang.get("playlist_queued", "✅ Added {0}:\n").format(len(tracks)) + txt,
                            )
                        except Exception:
                            pass
                    return

            # Download
            if not file.file_path:
                file.file_path = await yt.download(file.id, is_live=file.is_live, video=video)
                if not file.file_path:
                    await sent.edit_text(
                        "❌ <b>Download failed!</b>\n\n"
                        "• YouTube may have blocked the request\n"
                        "• Video may be region-blocked or private\n\n"
                        f"Support: {config.SUPPORT_CHAT}"
                    )
                    return

            # Play
            await tune.play_media(chat_id=chat_id, message=sent, media=file)

     
