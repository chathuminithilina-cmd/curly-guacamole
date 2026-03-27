import os
import asyncio
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Configuration ---
# Get these from https://my.telegram.org
API_ID = int(os.getenv("API_ID", "YOUR_API_ID"))
API_HASH = os.getenv("API_HASH", "YOUR_API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")

app = Client("video_dl_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

MAX_SIZE_GB = 2
DOWNLOAD_PATH = "downloads"
user_data = {}

if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

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
                # 2GB Limit Check
                if 0 < filesize <= (MAX_SIZE_GB * 1024 * 1024 * 1024) and height:
                    size_mb = round(filesize / (1024 * 1024), 1)
                    res_str = f"{height}p"
                    if not any(opt['res'] == res_str for opt in valid_options):
                        valid_options.append({'res': res_str, 'id': f['format_id'], 'size': f"{size_mb}MB"})
            
            return sorted(valid_options, key=lambda x: int(x['res'][:-1]), reverse=True), info.get('title')
        except Exception as e:
            print(f"Format Error: {e}")
            return [], None

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("🚀 **2GB High-Speed Downloader Ready.**\nSend me a link to begin.")

@app.on_message(filters.text & filters.private)
async def handle_url(client, message):
    url = message.text
    if "http" not in url: return

    status = await message.reply_text("🔍 Analyzing link...")
    qualities, title = get_formats(url)

    if not qualities:
        await status.edit("❌ No formats found under 2GB.")
        return

    user_data[message.from_user.id] = {"url": url, "title": title}
    
    buttons = [[InlineKeyboardButton(f"{q['res']} ({q['size']})", callback_data=q['id'])] for q in qualities]
    await status.edit(f"🎬 **{title}**\nSelect quality:", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query()
async def download_logic(client, callback_query):
    format_id = callback_query.data
    uid = callback_query.from_user.id
    data = user_data.get(uid)
    
    if not data:
        await callback_query.answer("Session expired. Send link again.", show_alert=True)
        return

    file_path = f"{DOWNLOAD_PATH}/{uid}_{format_id}.mp4"
    await callback_query.message.edit(f"📥 **Downloading:** {data['title']}\nPlease wait...")

    ydl_opts = {
        'format': f'{format_id}+bestaudio/best',
        'outtmpl': file_path,
        'merge_output_format': 'mp4',
        'quiet': True,
        'nocheckcertificate': True
    }

    try:
        # Download
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([data['url']]))

        await callback_query.message.edit("📤 **Uploading to Telegram...** (Up to 2GB)")
        
        # Upload using Pyrogram (Supports 2GB)
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
