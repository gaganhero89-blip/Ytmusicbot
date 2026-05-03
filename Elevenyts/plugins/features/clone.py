"""
Clone System — Yt Vibe Music Bot
Allows anyone to clone the bot with their own token.
Each user gets 1 clone with full customization.
"""

import asyncio
import os
import sys
from datetime import datetime

from pyrogram import Client, enums, filters, types
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Elevenyts import app, config, db, lang

# ============================================================
# DATABASE HELPERS (stored in MongoDB via db)
# Collection: "clones"
# Document structure:
# {
#   "user_id": int,
#   "bot_token": str,
#   "bot_username": str,
#   "bot_name": str,
#   "start_img": str,
#   "ping_img": str,
#   "support_chat": str,
#   "support_channel": str,
#   "welcome_text": str,
#   "created_at": datetime,
#   "active": bool
# }
# ============================================================

CLONE_COLLECTION = "clones"


async def get_clone(user_id: int) -> dict | None:
    return await db.db[CLONE_COLLECTION].find_one({"user_id": user_id})


async def save_clone(data: dict):
    await db.db[CLONE_COLLECTION].update_one(
        {"user_id": data["user_id"]},
        {"$set": data},
        upsert=True,
    )


async def delete_clone(user_id: int):
    await db.db[CLONE_COLLECTION].delete_one({"user_id": user_id})


# ============================================================
# RUNNING CLONES (in-memory: user_id -> pyrogram Client)
# ============================================================
running_clones: dict[int, Client] = {}


async def launch_clone(user_id: int, clone_data: dict):
    """Start a cloned bot as a Pyrogram client."""
    token = clone_data["bot_token"]
    bot_name = clone_data.get("bot_name", "Clone Bot")

    # Build custom config for this clone
    clone_config = type("CloneConfig", (), {
        "API_ID": config.API_ID,
        "API_HASH": config.API_HASH,
        "BOT_TOKEN": token,
        "OWNER_ID": user_id,
        "MONGO_URL": config.MONGO_URL,
        "START_IMG": clone_data.get("start_img", config.START_IMG),
        "PING_IMG": clone_data.get("ping_img", config.PING_IMG),
        "SUPPORT_CHAT": clone_data.get("support_chat", config.SUPPORT_CHAT),
        "SUPPORT_CHANNEL": clone_data.get("support_channel", config.SUPPORT_CHANNEL),
        "DURATION_LIMIT": config.DURATION_LIMIT,
        "QUEUE_LIMIT": config.QUEUE_LIMIT,
    })()

    client = Client(
        name=f"clone_{user_id}",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=token,
        in_memory=True,
    )

    # Register /start handler for this clone
    @client.on_message(filters.command("start") & filters.private)
    async def clone_start(_, message: types.Message):
        welcome = clone_data.get(
            "welcome_text",
            f"👋 Hello {message.from_user.first_name}!\n\n🎵 Welcome to <b>{bot_name}</b>!\n\nUse /play to start music."
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ Add Me", url=f"https://t.me/{clone_data.get('bot_username', '')}?startgroup=true"),
                InlineKeyboardButton("💬 Support", url=clone_data.get("support_chat", config.SUPPORT_CHAT)),
            ],
            [
                InlineKeyboardButton("📢 Channel", url=clone_data.get("support_channel", config.SUPPORT_CHANNEL)),
            ],
        ])
        try:
            await message.reply_photo(
                photo=clone_data.get("start_img", config.START_IMG),
                caption=welcome,
                reply_markup=keyboard,
            )
        except Exception:
            await message.reply_text(welcome, reply_markup=keyboard)

    # Register /ping for clone
    @client.on_message(filters.command("ping") & ~filters.bot)
    async def clone_ping(_, message: types.Message):
        start = datetime.now()
        msg = await message.reply_text("🏓 Pinging...")
        end = datetime.now()
        ms = (end - start).microseconds // 1000
        await msg.edit_text(f"🏓 Pong!\n⚡ Latency: <code>{ms}ms</code>")

    # Register /mybot — owner sees their clone info
    @client.on_message(filters.command("mybot") & filters.private)
    async def clone_mybot(_, message: types.Message):
        if message.from_user.id != user_id:
            return
        data = await get_clone(user_id)
        if not data:
            return await message.reply_text("❌ Clone data not found.")
        await message.reply_text(
            f"🤖 <b>Your Clone Bot Info</b>\n\n"
            f"📛 <b>Name:</b> {data.get('bot_name', 'N/A')}\n"
            f"🔗 <b>Username:</b> @{data.get('bot_username', 'N/A')}\n"
            f"🖼 <b>Start Image:</b> {'Custom ✅' if data.get('start_img') != config.START_IMG else 'Default'}\n"
            f"💬 <b>Support:</b> {data.get('support_chat', 'Default')}\n"
            f"📢 <b>Channel:</b> {data.get('support_channel', 'Default')}\n"
            f"📅 <b>Created:</b> {data.get('created_at', 'N/A')}\n\n"
            f"<i>Use /customizebot to change settings</i>"
        )

    # Register /customizebot — show customization menu
    @client.on_message(filters.command("customizebot") & filters.private)
    async def clone_customize(_, message: types.Message):
        if message.from_user.id != user_id:
            return
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📛 Bot Name", callback_data="cust_name"),
             InlineKeyboardButton("🖼 Start Image", callback_data="cust_startimg")],
            [InlineKeyboardButton("🏓 Ping Image", callback_data="cust_pingimg"),
             InlineKeyboardButton("💬 Support Chat", callback_data="cust_support")],
            [InlineKeyboardButton("📢 Channel Link", callback_data="cust_channel"),
             InlineKeyboardButton("👋 Welcome Text", callback_data="cust_welcome")],
            [InlineKeyboardButton("📊 Bot Stats", callback_data="cust_stats"),
             InlineKeyboardButton("🗑️ Delete Clone", callback_data="cust_delete")],
        ])
        await message.reply_text(
            "🎨 <b>Customize Your Bot</b>\n\nChoose what you want to change:",
            reply_markup=keyboard,
        )

    # Handle customization callbacks
    @client.on_callback_query(filters.regex("^cust_"))
    async def clone_cust_callback(_, query: types.CallbackQuery):
        if query.from_user.id != user_id:
            return await query.answer("❌ Not your bot!", show_alert=True)

        action = query.data

        prompts = {
            "cust_name": ("📛 Send your new <b>bot display name</b>:", "bot_name"),
            "cust_startimg": ("🖼 Send new <b>start image URL</b>:", "start_img"),
            "cust_pingimg": ("🏓 Send new <b>ping image URL</b>:", "ping_img"),
            "cust_support": ("💬 Send your <b>support chat link</b>:", "support_chat"),
            "cust_channel": ("📢 Send your <b>channel link</b>:", "support_channel"),
            "cust_welcome": ("👋 Send your <b>welcome message</b> (HTML supported):", "welcome_text"),
        }

        if action == "cust_stats":
            data = await get_clone(user_id)
            groups = await db.db["chats"].count_documents({})
            users = await db.db["users"].count_documents({})
            await query.message.edit_text(
                f"📊 <b>Bot Statistics</b>\n\n"
                f"👥 <b>Total Users:</b> {users}\n"
                f"🏠 <b>Total Groups:</b> {groups}\n"
                f"📛 <b>Bot Name:</b> {data.get('bot_name', 'N/A')}\n"
                f"🔗 <b>Username:</b> @{data.get('bot_username', 'N/A')}\n"
                f"📅 <b>Since:</b> {data.get('created_at', 'N/A')}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Back", callback_data="cust_back")
                ]])
            )
            return

        if action == "cust_delete":
            await query.message.edit_text(
                "⚠️ <b>Are you sure you want to delete your clone?</b>\n\nThis cannot be undone!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Yes, Delete", callback_data="cust_confirm_delete"),
                     InlineKeyboardButton("❌ Cancel", callback_data="cust_back")]
                ])
            )
            return

        if action == "cust_confirm_delete":
            await delete_clone(user_id)
            await query.message.edit_text("🗑️ Clone deleted. Bot will stop soon.")
            await asyncio.sleep(2)
            await client.stop()
            running_clones.pop(user_id, None)
            return

        if action == "cust_back":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📛 Bot Name", callback_data="cust_name"),
                 InlineKeyboardButton("🖼 Start Image", callback_data="cust_startimg")],
                [InlineKeyboardButton("🏓 Ping Image", callback_data="cust_pingimg"),
                 InlineKeyboardButton("💬 Support Chat", callback_data="cust_support")],
                [InlineKeyboardButton("📢 Channel Link", callback_data="cust_channel"),
                 InlineKeyboardButton("👋 Welcome Text", callback_data="cust_welcome")],
                [InlineKeyboardButton("📊 Bot Stats", callback_data="cust_stats"),
                 InlineKeyboardButton("🗑️ Delete Clone", callback_data="cust_delete")],
            ])
            await query.message.edit_text(
                "🎨 <b>Customize Your Bot</b>\n\nChoose what you want to change:",
                reply_markup=keyboard,
            )
            return

        if action in prompts:
            prompt_text, field_key = prompts[action]
            await query.message.edit_text(prompt_text)
            # Wait for next message
            try:
                response = await client.listen(query.message.chat.id, timeout=60)
                new_value = response.text.strip()
                await save_clone({"user_id": user_id, field_key: new_value})
                # Update in-memory clone_data
                clone_data[field_key] = new_value
                await response.reply_text(f"✅ Updated successfully!")
            except asyncio.TimeoutError:
                await query.message.reply_text("⏰ Timed out. Try again.")

    await client.start()
    me = await client.get_me()

    # Update bot username in db
    clone_data["bot_username"] = me.username or ""
    clone_data["bot_name"] = me.first_name or "Clone Bot"
    await save_clone(clone_data)

    running_clones[user_id] = client
    return me


# ============================================================
# MAIN BOT — /clone COMMAND
# ============================================================

@app.on_message(filters.command("clone") & filters.private)
async def clone_command(_, message: types.Message):
    """
    /clone <bot_token>
    Anyone can clone the bot with their own token.
    Only 1 clone per user allowed.
    """
    if not message.from_user:
        return

    user_id = message.from_user.id

    # Check if already has a clone
    existing = await get_clone(user_id)
    if existing:
        return await message.reply_text(
            "⚠️ <b>You already have a clone!</b>\n\n"
            f"🤖 <b>Bot:</b> @{existing.get('bot_username', 'N/A')}\n\n"
            "Use <code>/deleteclone</code> to remove it first, or <code>/customizebot</code> to manage it.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎨 Customize", callback_data="open_customize"),
                InlineKeyboardButton("🗑️ Delete", callback_data="delete_my_clone"),
            ]])
        )

    # Check token provided
    if len(message.command) < 2:
        return await message.reply_text(
            "❌ <b>Please provide your bot token!</b>\n\n"
            "📖 <b>Usage:</b> <code>/clone YOUR_BOT_TOKEN</code>\n\n"
            "💡 Get a token from @BotFather"
        )

    token = message.command[1].strip()

    # Basic token validation
    if ":" not in token or len(token) < 30:
        return await message.reply_text(
            "❌ <b>Invalid token format!</b>\n\n"
            "Token should look like: <code>123456789:ABCdefGHI...</code>"
        )

    status_msg = await message.reply_text("⏳ <b>Creating your clone bot...</b>")

    try:
        clone_data = {
            "user_id": user_id,
            "bot_token": token,
            "start_img": config.START_IMG,
            "ping_img": config.PING_IMG,
            "support_chat": config.SUPPORT_CHAT,
            "support_channel": config.SUPPORT_CHANNEL,
            "welcome_text": "",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "active": True,
        }

        me = await launch_clone(user_id, clone_data)

        await status_msg.edit_text(
            f"✅ <b>Clone Created Successfully!</b>\n\n"
            f"🤖 <b>Bot:</b> @{me.username}\n"
            f"📛 <b>Name:</b> {me.first_name}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎨 <b>Customize your bot:</b>\n"
            f"• /customizebot — Full customization menu\n"
            f"• /mybot — View your bot info\n"
            f"• /deleteclone — Delete your clone\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<i>Message your bot directly to customize it!</i>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"🤖 Open @{me.username}", url=f"https://t.me/{me.username}")
            ]])
        )

    except Exception as e:
        await status_msg.edit_text(
            f"❌ <b>Failed to create clone!</b>\n\n"
            f"<b>Reason:</b> <code>{str(e)[:200]}</code>\n\n"
            f"Make sure:\n"
            f"• Token is correct\n"
            f"• Bot exists on Telegram\n"
            f"• Token is not already in use"
        )


@app.on_message(filters.command("deleteclone") & filters.private)
async def delete_clone_command(_, message: types.Message):
    """Delete user's clone bot."""
    user_id = message.from_user.id
    existing = await get_clone(user_id)

    if not existing:
        return await message.reply_text("❌ You don't have any clone!")

    # Stop running clone
    if user_id in running_clones:
        try:
            await running_clones[user_id].stop()
        except Exception:
            pass
        running_clones.pop(user_id, None)

    await delete_clone(user_id)
    await message.reply_text(
        "🗑️ <b>Clone deleted successfully!</b>\n\n"
        "Use /clone to create a new one anytime."
    )


@app.on_message(filters.command("myclone") & filters.private)
async def my_clone_command(_, message: types.Message):
    """Show user's clone info."""
    user_id = message.from_user.id
    existing = await get_clone(user_id)

    if not existing:
        return await message.reply_text(
            "❌ <b>You don't have a clone yet!</b>\n\n"
            "Use <code>/clone YOUR_BOT_TOKEN</code> to create one."
        )

    status = "🟢 Running" if user_id in running_clones else "🔴 Stopped"

    await message.reply_text(
        f"🤖 <b>Your Clone Bot</b>\n\n"
        f"📛 <b>Name:</b> {existing.get('bot_name', 'N/A')}\n"
        f"🔗 <b>Username:</b> @{existing.get('bot_username', 'N/A')}\n"
        f"📊 <b>Status:</b> {status}\n"
        f"📅 <b>Created:</b> {existing.get('created_at', 'N/A')}\n\n"
        f"<b>Customizations:</b>\n"
        f"🖼 Start Image: {'Custom ✅' if existing.get('start_img') != config.START_IMG else 'Default'}\n"
        f"💬 Support: {'Custom ✅' if existing.get('support_chat') != config.SUPPORT_CHAT else 'Default'}\n"
        f"👋 Welcome: {'Custom ✅' if existing.get('welcome_text') else 'Default'}\n",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🤖 Open Bot", url=f"https://t.me/{existing.get('bot_username', '')}")],
            [InlineKeyboardButton("🗑️ Delete Clone", callback_data="delete_my_clone")]
        ])
    )


@app.on_callback_query(filters.regex("^delete_my_clone$"))
async def delete_clone_callback(_, query: types.CallbackQuery):
    user_id = query.from_user.id
    existing = await get_clone(user_id)
    if not existing:
        return await query.answer("No clone found!", show_alert=True)

    if user_id in running_clones:
        try:
            await running_clones[user_id].stop()
        except Exception:
            pass
        running_clones.pop(user_id, None)

    await delete_clone(user_id)
    await query.message.edit_text("🗑️ Clone deleted successfully!")


# ============================================================
# AUTO-RESTART CLONES ON BOT START
# ============================================================

async def restart_all_clones():
    """Restart all active clones when main bot starts."""
    try:
        cursor = db.db[CLONE_COLLECTION].find({"active": True})
        async for clone_data in cursor:
            user_id = clone_data["user_id"]
            try:
                await launch_clone(user_id, clone_data)
                print(f"✅ Clone restarted for user {user_id}")
            except Exception as e:
                print(f"❌ Failed to restart clone for {user_id}: {e}")
    except Exception as e:
        print(f"❌ Error restarting clones: {e}")


# Call this from your main bot startup file:
# asyncio.create_task(restart_all_clones())
