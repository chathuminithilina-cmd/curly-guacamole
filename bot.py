import os
import shutil
import asyncio
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand

# --- Configuration (Set these in Railway Variables) ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "your_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_token")

app = Client("video_dl_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

MAX_SIZE_GB = 2
DOWNLOAD_PATH = "downloads"
COOKIE_FILE = "cookies.txt"
user_data = {}

# Ensure download directory exists
if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# Common Headers to bypass "Bot" blocks
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': 'https://www.pornhub.com/',
    'Connection': 'keep-alive',
}

# --- Helper Functions ---
def get_formats(url):
    ydl_opts = {
        'quiet': True, 
        'no_warnings': True,
        'nocheckcertificate': True,
        'http_headers': HEADERS,
    }
    
    if os.path.exists(COOKIE_FILE):
        ydl_opts['cookiefile'] = COOKIE_FILE

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            valid_options = []
            
            for f in formats:
                filesize = f.get('filesize') or f.get('filesize_approx') or 0
                height = f.get('height')
                # Filter for videos under 2GB with a valid resolution
                if 0 < filesize <= (MAX_SIZE_GB * 1024 * 1024 * 1024) and height:
                    size_mb = round(filesize / (1024 * 1024), 1)
                    res_str = f"{height}p"
                    # Avoid duplicates (keep only one format per resolution)
                    if not any(opt['res'] == res_str for opt in valid_options):
                        valid_options.append({'res': res_str, 'id': f['format_id'], 'size': f"{size_mb}MB"})
            
            # Sort by resolution (highest first)
            sorted_options = sorted(valid_options, key=lambda x: int(x['res'][:-1]), reverse=True)
            return sorted_options, info.get('title')
        except Exception as e:
            print(f"Extraction Error: {e}")
            return [], str(e)

# --- Command Handlers ---

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await client.set_bot_commands([
        BotCommand("start", "Refresh the bot"),
        BotCommand("status", "Check disk space"),
        BotCommand("help", "Usage guide")
    ])
    welcome = (
        f"👋 **Hi {message.from_user.first_name}!**\n\n"
        "I am a 2GB High-Speed Video Downloader.\n\n"
        "🛠 **How to use:**\n"
        "1. Send any video link.\n"
        "2. Choose your quality.\n"
        "3. Wait for the upload.\n\n"
        "🍪 **Cookies:** Send a `cookies.txt` file to update me."
    )
    await message.reply_text(welcome)

@app.on_message(filters.command("status") & filters.private)
async def status_cmd(client, message):
    total, used, free = shutil.disk_usage("/")
    cookie_status = "✅ Active" if os.path.exists(COOKIE_FILE) else "❌ Not Found"
    status_text = (
        "🖥 **Server Status (Railway)**\n\n"
        f"📊 **Free Space:** {free // (2**30)} GB\n"
        f"🍪 **Cookies:** {cookie_status}\n"
        "📂 **Storage:** Temporary (Auto-clean)"
    )
    await message.reply_text(status_text)

# --- Cookie File Handler ---
@app.on_message(filters.document & filters.private)
async def handle_cookies(client, message):
    if message.document.file_name == "cookies.txt":
        await message.download(file_name=COOKIE_FILE)
        await message.reply_text("✅ **Cookies updated!** Future requests will use this file.")
    else:
        await message.reply_text("❌ Error: File must be named exactly `cookies.txt`.")

# --- URL & Download Logic ---

@app.on_message(filters.text & filters.private & ~filters.command(["start", "status", "help"]))
async def handle_url(client, message):
    url = message.text
    if "http" not in url: return
    
    status = await message.reply_text("🔍 **Analyzing Link...**")
    qualities, title_or_error = get_formats(url)

    if not qualities:
        return await status.edit(f"❌ **Failed!**\n\nError: `{title_or_error}`\n\n*Tip: Ensure your cookies.txt is fresh and valid.*")

    user_data[message.from_user.id] = {"url": url, "title": title_or_error}
    buttons = [[InlineKeyboardButton(f"🎬 {q['res']} ({q['size']})", callback_data=q['id'])] for q in qualities]
    
    await status.edit(
        f"🎥 **{title_or_error[:60]}**\n\nSelect quality:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query()
async def download_callback(client, callback_query):
    format_id = callback_query.data
    uid = callback_query.from_user.id
    data = user_data.get(uid)
    
    if not data:
        return await callback_query.answer("Session expired. Please send the link again.", show_alert=True)

    file_path = f"{DOWNLOAD_PATH}/{uid}_{format_id}.mp4"
    await callback_query.message.edit(f"📥 **Downloading...**\n`{data['title']}`")

    ydl_opts = {
        'format': f'{format_id}+bestaudio/best',
        'outtmpl': file_path,
        'merge_output_format': 'mp4',
        'nocheckcertificate': True,
        'http_headers': HEADERS,
    }
    if os.path.exists(COOKIE_FILE):
        ydl_opts['cookiefile'] = COOKIE_FILE

    try:
        # Download in background
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([data['url']]))

        await callback_query.message.edit("📤 **Uploading to Telegram...**\n(Files near 2GB take longer)")
        
        await client.send_video(
            chat_id=callback_query.message.chat.id,
            video=file_path,
            caption=f"✅ **{data['title']}**",
            supports_streaming=True
        )
        await callback_query.message.delete()
    except Exception as e:
        await callback_query.message.edit(f"❌ **Error during download/upload:**\n`{str(e)}`")
    finally:
        # Cleanup file to save Railway disk space
        if os.path.exists(file_path):
            os.remove(file_path)

print("Bot is starting...")
app.run()
