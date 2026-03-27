import os
import shutil
import asyncio
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand

# --- Configuration ---
API_ID = int(os.getenv("API_ID", "YOUR_API_ID"))
API_HASH = os.getenv("API_HASH", "YOUR_API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")

app = Client("video_dl_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

MAX_SIZE_GB = 2
DOWNLOAD_PATH = "downloads"
user_data = {}

if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# --- Helper Functions ---
def get_formats(url):
    ydl_opts = {'quiet': True, 'no_warnings': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            valid_options = []
            for f in formats:
                filesize = f.get('filesize') or f.get('filesize_approx') or 0
                height = f.get('height')
                if 0 < filesize <= (MAX_SIZE_GB * 1024 * 1024 * 1024) and height:
                    size_mb = round(filesize / (1024 * 1024), 1)
                    res_str = f"{height}p"
                    if not any(opt['res'] == res_str for opt in valid_options):
                        valid_options.append({'res': res_str, 'id': f['format_id'], 'size': f"{size_mb}MB"})
            return sorted(valid_options, key=lambda x: int(x['res'][:-1]), reverse=True), info.get('title')
        except Exception:
            return [], None

# --- Handlers ---

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    # Setting the Command List in the Telegram Menu
    await client.set_bot_commands([
        BotCommand("start", "Refresh the bot"),
        BotCommand("help", "How to use the bot"),
        BotCommand("status", "Check server disk space")
    ])
    
    welcome_text = (
        f"✨ **Welcome, {message.from_user.first_name}!**\n\n"
        "I am a High-Speed Video Downloader Bot.\n"
        "I support files up to **2GB** (High Quality).\n\n"
        "📜 **How to use:**\n"
        "1. Send me any video link.\n"
        "2. Wait for me to analyze the qualities.\n"
        "3. Choose your preferred resolution.\n\n"
        "⚡ *Powered by yt-dlp & Pyrogram*"
    )
    await message.reply_text(welcome_text)

@app.on_message(filters.command("help") & filters.private)
async def help_cmd(client, message):
    help_text = (
        "📖 **Help Menu**\n\n"
        "• **Supported Sites:** Most video platforms.\n"
        "• **Limit:** Max 2GB per file.\n"
        "• **Quality:** Choose from 144p up to 4K (if available).\n\n"
        "🛠 **Commands:**\n"
        "/start - Start the bot\n"
        "/status - Check Railway server health\n"
        "/help - Show this message"
    )
    await message.reply_text(help_text)

@app.on_message(filters.command("status") & filters.private)
async def status_cmd(client, message):
    total, used, free = shutil.disk_usage("/")
    status_text = (
        "🖥 **Server Status (Railway)**\n\n"
        f"📊 **Disk Total:** {total // (2**30)} GB\n"
        f"✅ **Disk Free:** {free // (2**30)} GB\n"
        f"⚠️ **Limit:** 2GB per download"
    )
    await message.reply_text(status_text)

@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "status"]))
async def handle_url(client, message):
    url = message.text
    if "http" not in url:
        return await message.reply_text("❌ Please send a valid link starting with http")

    status = await message.reply_text("🔍 **Analyzing link...** Please wait.")
    qualities, title = get_formats(url)

    if not qualities:
        return await status.edit("❌ No formats found or video is too large (Over 2GB).")

    user_data[message.from_user.id] = {"url": url, "title": title}
    
    buttons = [[InlineKeyboardButton(f"🎬 {q['res']} ({q['size']})", callback_data=q['id'])] for q in qualities]
    await status.edit(
        f"🎥 **Title:** `{title[:50]}...`\n\nSelect the quality to download:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query()
async def download_logic(client, callback_query):
    format_id = callback_query.data
    uid = callback_query.from_user.id
    data = user_data.get(uid)
    
    if not data:
        return await callback_query.answer("Session expired. Send link again.", show_alert=True)

    file_path = f"{DOWNLOAD_PATH}/{uid}_{format_id}.mp4"
    await callback_query.message.edit(f"📥 **Downloading...**\n`{data['title']}`")

    ydl_opts = {
        'format': f'{format_id}+bestaudio/best/best',
        'outtmpl': file_path,
        'merge_output_format': 'mp4',
        'quiet': True,
        'nocheckcertificate': True
    }

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([data['url']]))

        await callback_query.message.edit("📤 **Uploading to Telegram...**\n(Files up to 2GB may take time)")
        
        await client.send_video(
            chat_id=callback_query.message.chat.id,
            video=file_path,
            caption=f"✅ **{data['title']}**\n\n@YourBotName",
            supports_streaming=True
        )
        await callback_query.message.delete()
    except Exception as e:
        await callback_query.message.edit(f"❌ **Error:** `{str(e)}`")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

app.run()
