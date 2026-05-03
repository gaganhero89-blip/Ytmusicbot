from pyrogram import enums, errors, filters, types
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Elevenyts import app, config, db, lang
from Elevenyts.helpers import buttons, utils


@app.on_message(filters.command(["help"]) & filters.private & ~app.bl_users)
@lang.language()
async def _help(_, m: types.Message):
    """Handle /help command in private chats - shows help menu with image."""
    try:
        await m.delete()
    except Exception:
        pass

    try:
        await m.reply_photo(
            photo=config.START_IMG,
            caption=m.lang["help_menu"],
            reply_markup=buttons.help_markup(m.lang),
            quote=True,
        )
    except Exception:
        await m.reply_text(
            text=m.lang["help_menu"],
            reply_markup=buttons.help_markup(m.lang),
            quote=True,
        )


def build_start_keyboard(lang: dict, private: bool, is_owner: bool = False) -> InlineKeyboardMarkup:
    """
    Build start keyboard with colored URL buttons.
    URL buttons appear colored (green) in Telegram.
    Owner gets an extra 👑 Adam button on top.
    """
    keyboard = []

    # Owner button — only for owner, on top (callback so it's always visible)
    if is_owner and private:
        keyboard.append([
            InlineKeyboardButton("👑 ᴀᴅᴀᴍ — ᴏᴡɴᴇʀ ᴘᴀɴᴇʟ 👑", callback_data="owner_panel")
        ])

    # Row 1 — colored URL buttons (these show as green in Telegram)
    keyboard.append([
        InlineKeyboardButton("➕ " + lang.get("add_me", "Add Me"), url=f"https://t.me/{app.username}?startgroup=true"),
        InlineKeyboardButton("💬 " + lang.get("support", "Support"), url=config.SUPPORT_CHAT),
    ])

    # Row 2
    keyboard.append([
        InlineKeyboardButton("📢 " + lang.get("channel", "Channel"), url=config.SUPPORT_CHANNEL),
        InlineKeyboardButton("❓ " + lang.get("help", "Help"), url=f"https://t.me/{app.username}?start=help"),
    ])

    return InlineKeyboardMarkup(keyboard)


def build_group_keyboard(lang: dict) -> InlineKeyboardMarkup:
    """Build keyboard for group start message."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ " + lang.get("add_me", "Add Me"), url=f"https://t.me/{app.username}?startgroup=true"),
            InlineKeyboardButton("💬 " + lang.get("support", "Support"), url=config.SUPPORT_CHAT),
        ]
    ])


@app.on_message(filters.command(["start"]))
@lang.language()
async def start(_, message: types.Message):
    """
    Handle /start command - welcome message for users.

    - In private chat: Shows welcome message with inline buttons
    - In group chat: Shows short welcome message
    - Owner gets extra 👑 Adam button on top
    - Adds new users to database
    - Sends log to logger group for new users
    """
    # Auto-delete command message in group chats
    if message.chat.type != enums.ChatType.PRIVATE:
        try:
            await message.delete()
        except Exception:
            pass

    # Skip if message from channel or anonymous admin
    if not message.from_user:
        return

    # Check if user is blacklisted
    if message.from_user.id in app.bl_users and message.from_user.id not in db.notified:
        return await message.reply_text(message.lang["bl_user_notify"])

    # If /start help, show help menu
    if len(message.command) > 1 and message.command[1] == "help":
        return await _help(_, message)

    # Determine if chat is private or group
    private = message.chat.type == enums.ChatType.PRIVATE

    # Check if owner — ensure int comparison
    is_owner = message.from_user.id == int(config.OWNER_ID)

    # Choose appropriate welcome message (UNCHANGED from original)
    _text = (
        message.lang["start_pm"].format(message.from_user.first_name, app.name)
        if private
        else message.lang["start_gp"].format(app.name)
    )

    # Build keyboard with colored buttons + owner button if applicable
    if private:
        key = build_start_keyboard(message.lang, private=True, is_owner=is_owner)
    else:
        key = build_group_keyboard(message.lang)

    try:
        await message.reply_photo(
            photo=config.START_IMG,
            caption=_text,
            reply_markup=key,
            quote=not private,
        )
    except errors.ChatSendPhotosForbidden:
        await message.reply_text(
            text=_text,
            reply_markup=key,
            quote=not private,
        )

    # For private chats, add user to database if new
    if private:
        if await db.is_user(message.from_user.id):
            return
        await utils.send_log(message)
        return await db.add_user(message.from_user.id)


@app.on_message(filters.command(["playmode", "settings"]) & filters.group & ~app.bl_users)
@lang.language()
async def settings(_, message: types.Message):
    """Handle /playmode or /settings command - show group settings."""
    try:
        await message.delete()
    except Exception:
        pass

    admin_only = await db.get_play_mode(message.chat.id)
    _language = "en"
    await message.reply_text(
        text=message.lang["start_settings"].format(message.chat.title),
        reply_markup=buttons.settings_markup(
            message.lang, admin_only, _language, message.chat.id
        ),
        quote=True,
    )


@app.on_callback_query(filters.regex("^owner_panel$"))
async def owner_panel(_, query: types.CallbackQuery):
    """Owner panel — shows owner-only options."""
    if query.from_user.id != int(config.OWNER_ID):
        return await query.answer("❌ Sirf Owner use kar sakta hai!", show_alert=True)

    await query.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Stats", callback_data="op_stats"),
             InlineKeyboardButton("📢 Broadcast", callback_data="op_broadcast")],
            [InlineKeyboardButton("🔄 Restart", callback_data="op_restart"),
             InlineKeyboardButton("🔧 Maintenance", callback_data="op_maintenance")],
            [InlineKeyboardButton("👥 Sudo Users", callback_data="op_sudo"),
             InlineKeyboardButton("🚫 Blacklist", callback_data="op_blacklist")],
            [InlineKeyboardButton("◀️ Back", callback_data="op_back")],
        ])
    )
    await query.answer("👑 Welcome, Adam!")


@app.on_callback_query(filters.regex("^op_back$"))
async def owner_panel_back(_, query: types.CallbackQuery):
    if query.from_user.id != int(config.OWNER_ID):
        return await query.answer("❌ Not allowed!", show_alert=True)
    # Restore original start keyboard
    key = build_start_keyboard(query.message.reply_markup and {}, private=True, is_owner=True)
    await query.message.edit_reply_markup(reply_markup=key)
    await query.answer()


@app.on_message(filters.new_chat_members, group=7)
@lang.language()
async def _new_member(_, message: types.Message):
    """Handle new member events - detect when bot is added to groups."""
    if message.chat.type != enums.ChatType.SUPERGROUP:
        return await message.chat.leave()

    for member in message.new_chat_members:
        if member.id == app.id:
            if await db.is_chat(message.chat.id):
                return
            await db.add_chat(message.chat.id)
                                 
