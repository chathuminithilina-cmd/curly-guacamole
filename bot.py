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

if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# --- Helper Functions ---
def get_formats(url):
    ydl_opts = {
        'quiet': True, 
        'no_warnings': True,
        'nocheckcertificate': True,
    }
    # Check if cookies exist on the server
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
                # 2GB Filter
                if 0 < filesize <= (MAX_SIZE_GB * 1024 * 1024 * 1024) and height:
                    size_mb = round(filesize / (1024 * 1024), 1)
                    res_str = f"{height}p"
                    if not any(opt['res'] == res_str for opt in valid_options):
                        valid_options.append({'res': res_str, 'id': f['format_id'], 'size': f"{size_mb}MB"})
            return sorted(valid_options, key=lambda x: int(x['res'][:-1]), reverse=True), info.get('title')
        except Exception as e:
            print(f"Extraction Error: {e}")
            return [], None

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
        "I can download videos up to **2GB**.\n"
        "Just send me a link to get started.\n\n"
        "🍪 **Tip:** To update cookies, just send me a `cookies.txt` file."
    )
    await message.reply_text(welcome)

@app.on_message(filters.command("status") & filters.private)
async def status_cmd(client, message):
    total, used, free = shutil.disk_usage("/")
    cookie_status = "✅ Active" if os.path.exists(COOKIE_FILE) else "❌ Not Found"
    status_text = (
        "🖥 **Server Status**\n\n"
        f"📊 **Free Space:** {free // (2**30)} GB\n"
        f"🍪 **Cookies:** {cookie_status}\n"
        f"⚡ **FFmpeg:** Installed"
    )
    await message.reply_text(status_text)

# --- Cookie File Handler ---
@app.on_message(filters.document & filters.private)
async def handle_cookies(client, message):
    if message.document.file_name == "cookies.txt":
        await message.download(file_name=COOKIE_FILE)
        await message.reply_text("✅ **Cookies updated successfully!**\nI will now use these for future downloads.")
    else:
        await message.reply_text("❌ Please send a file named exactly `cookies.txt`.")

# --- URL & Download Logic ---

@app.on_message(filters.text & filters.private & ~filters.command(["start", "status", "help"]))
async def handle_url(client, message):
    url = message.text
    if "http" not in url: return
    
    status = await message.reply_text("🔍 **Analyzing...** (using cookies if available)")
    qualities, title = get_formats(url)

    if not qualities:
        return await status.edit("❌ Failed to find formats. Ensure the link is valid and cookies are updated.")

    user_data[message.from_user.id] = {"url": url, "title": title}
    buttons = [[InlineKeyboardButton(f"🎬 {q['res']} ({q['size']})", callback_data=q['id'])] for q in qualities]
    
    await status.edit(
        f"🎥 **{title[:60]}**\n\nSelect quality:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query()
async def download_callback(client, callback_query):
    format_id = callback_query.data
    uid = callback_query.from_user.id
    data = user_data.get(uid)
    
    if not data:
        return await callback_query.answer("Session expired.", show_alert=True)

    file_path = f"{DOWNLOAD_PATH}/{uid}_{format_id}.mp4"
    await callback_query.message.edit(f"📥 **Downloading...**\n`{data['title']}`")

    ydl_opts = {
        'format': f'{format_id}+bestaudio/best',
        'outtmpl': file_path,
        'merge_output_format': 'mp4',
        'nocheckcertificate': True,
    }
    if os.path.exists(COOKIE_FILE):
        ydl_opts['cookiefile'] = COOKIE_FILE

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([data['url']]))

        await callback_query.message.edit("📤 **Uploading to Telegram...**")
        await client.send_video(
            chat_id=callback_query.message.chat.id,
            video=file_path,
            caption=f"✅ **{data['title']}**",
            supports_streaming=True
        )
        await callback_query.message.delete()
    except Exception as e:
        await callback_query.message.edit(f"❌ **Error:** `{str(e)}`")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

app.run()
