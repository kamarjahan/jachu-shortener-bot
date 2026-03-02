import asyncio
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

# --- Configuration ---
API_ID = "17875613"              # Get from my.telegram.org
API_HASH = "6798f54a7f74e94f2ef0923fba8a8377"          # Get from my.telegram.org
BOT_TOKEN = "7780022269:AAE6xCO3B7_Y6VfbW60zzyr6YzZuP33wz0U"        # Get from @BotFather
JACHU_API_KEY = "3529ceaf18de4043b0323b48f68f4e89" # Get from jachu.xyz

app = Client("jachu_shortener_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Simple in-memory state management to track user interactions
# Note: For production with thousands of users, consider using Redis or a Database here.
user_states = {}

# --- API Helper Function ---
async def shorten_url(url: str, slug: str = None) -> dict:
    """Calls the jachu.xyz API to shorten the URL."""
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

# --- Bot Commands & Handlers ---

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """Handles the /start command."""
    # Clear any existing state for the user
    user_states.pop(message.from_user.id, None)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Read Legal Docs 📜", url="https://jachu.xyz/legal")],
        [InlineKeyboardButton("Help❓", callback_data="help_info")]
    ])
    
    welcome_text = (
        "👋 Welcome to the Advanced URL Shortener!\n\n"
        "Just send me any long link (starting with http:// or https://), "
        "and I'll help you shorten it using the jachu.xyz API."
    )
    await message.reply_text(welcome_text, reply_markup=keyboard)

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_command(client: Client, message: Message):
    """Cancels the current operation."""
    user_id = message.from_user.id
    if user_id in user_states:
        user_states.pop(user_id)
        await message.reply_text("Operation cancelled. Send me a new link whenever you are ready.")
    else:
        await message.reply_text("Nothing to cancel. Send me a link to get started!")

@app.on_message(filters.regex(r"^https?://") & filters.private)
async def handle_url(client: Client, message: Message):
    """Detects URLs sent by the user and initiates the shortening process."""
    user_id = message.from_user.id
    url = message.text.strip()
    
    # Save the URL in the user's state
    user_states[user_id] = {"url": url, "step": "CHOOSE_MODE"}
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔀 Random Alias", callback_data="mode_random")],
        [InlineKeyboardButton("✍️ Custom Alias", callback_data="mode_custom")]
    ])
    
    await message.reply_text(
        f"Link received:\n`{url}`\n\nHow would you like to shorten it?", 
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@app.on_callback_query(filters.regex(r"^mode_"))
async def handle_callback_query(client: Client, callback_query: CallbackQuery):
    """Handles the inline button presses for Random vs Custom Alias."""
    user_id = callback_query.from_user.id
    mode = callback_query.data
    
    if user_id not in user_states or user_states[user_id].get("step") != "CHOOSE_MODE":
        await callback_query.answer("Session expired or invalid. Please send the link again.", show_alert=True)
        return

    if mode == "mode_random":
        # Process random alias immediately
        await callback_query.message.edit_text("⏳ Shortening your link...")
        url = user_states[user_id]["url"]
        
        result = await shorten_url(url)
        
        if result.get("status") == "success":
            short_url = result.get('short_url')
            await callback_query.message.edit_text(f"✅ **Success!**\n\nHere is your short link:\n{short_url}")
        else:
            await callback_query.message.edit_text(f"❌ **Error:** {result.get('message')}")
            
        # Clean up state
        user_states.pop(user_id, None)

    elif mode == "mode_custom":
        # Move state to waiting for alias input
        user_states[user_id]["step"] = "WAITING_FOR_ALIAS"
        await callback_query.message.edit_text(
            "Please type and send the custom alias you want to use.\n\n"
            "*(e.g., if you want jachu.xyz/my-link, just type `my-link`)*\n\n"
            "Send /cancel to abort."
        )

@app.on_message(filters.text & filters.private & ~filters.command(["start", "cancel"]))
async def handle_custom_alias(client: Client, message: Message):
    """Captures the custom alias sent by the user."""
    user_id = message.from_user.id
    
    if user_id in user_states and user_states[user_id].get("step") == "WAITING_FOR_ALIAS":
        alias = message.text.strip()
        url = user_states[user_id]["url"]
        
        processing_msg = await message.reply_text(f"⏳ Trying to claim alias `{alias}`...")
        
        result = await shorten_url(url, slug=alias)
        
        if result.get("status") == "success":
            short_url = result.get('short_url')
            await processing_msg.edit_text(f"✅ **Success!**\n\nHere is your short link:\n{short_url}")
            # Clean up state
            user_states.pop(user_id, None)
        else:
            # If it fails, keep the state intact so they can try another alias
            error_msg = result.get('message', 'Unknown error')
            await processing_msg.edit_text(
                f"❌ **Failed:** {error_msg}\n\n"
                f"The alias `{alias}` is likely already taken or invalid.\n"
                f"Please reply with a **different alias**, or send /cancel to abort."
            )

@app.on_callback_query(filters.regex("help_info"))
async def help_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("Send any valid URL to start shortening it. You can pick a random or custom alias!", show_alert=True)

if __name__ == "__main__":
    print("Bot is running...")
    app.run()
