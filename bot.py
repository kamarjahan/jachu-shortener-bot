import os
import asyncio
import aiohttp
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
import logging

# Enable basic logging to see errors in the Render dashboard
logging.basicConfig(level=logging.INFO)

# --- Configuration using Environment Variables ---
try:
    API_ID = int(os.environ.get("API_ID", 0))
except ValueError:
    API_ID = 0
    
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
JACHU_API_KEY = os.environ.get("JACHU_API_KEY", "")

app = Client("jachu_shortener_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_states = {}

# --- Dummy Web Server for Render ---
# Render requires Web Services to bind to a port, otherwise it kills the app.
async def health_check(request):
    return web.Response(text="Bot is alive and running!")

async def start_web_server():
    server = web.Application()
    server.router.add_get('/', health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Dummy web server started on port {port}")

# --- API Helper Function ---
async def shorten_url(url: str, slug: str = None) -> dict:
    api_url = "https://jachu.xyz/api/create"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": JACHU_API_KEY
    }
    payload = {"url": url}
    if slug:
        payload["slug"] = slug

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_url, headers=headers, json=payload) as response:
                return await response.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

# --- Bot Commands ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_states.pop(message.from_user.id, None)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Read Legal Docs 📜", url="https://jachu.xyz/legal")],
        [InlineKeyboardButton("Help❓", callback_data="help_info")]
    ])
    await message.reply_text("👋 Welcome! Send me a link and I'll shorten it via jachu.xyz.", reply_markup=keyboard)

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_command(client: Client, message: Message):
    if message.from_user.id in user_states:
        user_states.pop(message.from_user.id)
        await message.reply_text("Operation cancelled.")
    else:
        await message.reply_text("Nothing to cancel.")

@app.on_message(filters.regex(r"^https?://") & filters.private)
async def handle_url(client: Client, message: Message):
    user_id = message.from_user.id
    url = message.text.strip()
    user_states[user_id] = {"url": url, "step": "CHOOSE_MODE"}
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔀 Random Alias", callback_data="mode_random")],
        [InlineKeyboardButton("✍️ Custom Alias", callback_data="mode_custom")]
    ])
    await message.reply_text(f"Link received:\n`{url}`\n\nHow would you like to shorten it?", reply_markup=keyboard, disable_web_page_preview=True)

@app.on_callback_query(filters.regex(r"^mode_"))
async def handle_callback_query(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    mode = callback_query.data
    
    if user_id not in user_states or user_states[user_id].get("step") != "CHOOSE_MODE":
        return await callback_query.answer("Session expired. Send link again.", show_alert=True)

    if mode == "mode_random":
        await callback_query.message.edit_text("⏳ Shortening...")
        result = await shorten_url(user_states[user_id]["url"])
        if result.get("status") == "success":
            await callback_query.message.edit_text(f"✅ **Success!**\n{result.get('short_url')}")
        else:
            await callback_query.message.edit_text(f"❌ **Error:** {result.get('message')}")
        user_states.pop(user_id, None)

    elif mode == "mode_custom":
        user_states[user_id]["step"] = "WAITING_FOR_ALIAS"
        await callback_query.message.edit_text("Please type your custom alias (e.g., `my-link`). Send /cancel to abort.")

@app.on_message(filters.text & filters.private & ~filters.command(["start", "cancel"]))
async def handle_custom_alias(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_states and user_states[user_id].get("step") == "WAITING_FOR_ALIAS":
        alias = message.text.strip()
        processing_msg = await message.reply_text(f"⏳ Claiming alias `{alias}`...")
        
        result = await shorten_url(user_states[user_id]["url"], slug=alias)
        
        if result.get("status") == "success":
            await processing_msg.edit_text(f"✅ **Success!**\n{result.get('short_url')}")
            user_states.pop(user_id, None)
        else:
            await processing_msg.edit_text(f"❌ **Failed:** {result.get('message')}\n\nAlias likely taken. Reply with a **different alias**, or /cancel.")

@app.on_callback_query(filters.regex("help_info"))
async def help_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("Send any valid URL to start!", show_alert=True)

# --- Main Async Loop ---
async def main():
    # 1. Safety check for credentials
    if not API_ID or not API_HASH or not BOT_TOKEN:
        logging.error("❌ CRITICAL ERROR: Missing API_ID, API_HASH, or BOT_TOKEN. Please set these in Render Environment Variables!")
        return

    # 2. Start the dummy web server so Render doesn't crash the app
    await start_web_server()

    # 3. Start the Pyrogram bot
    logging.info("Starting Pyrogram bot...")
    await app.start()
    logging.info("Bot is successfully running!")
    
    # Keep the script running
    await idle()
    
    # Cleanup on shutdown
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
