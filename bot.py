import os
import shutil
import asyncio
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand

# --- Config (Set in Railway Variables) ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "your_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_token")

app = Client("video_dl_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

DOWNLOAD_PATH = "downloads"
COOKIE_FILE = "cookies.txt"
user_data = {}

if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# Aggressive headers to look like a Singapore-based Chrome browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'en-SG,en-US;q=0.9,en;q=0.8',
    'Referer': 'https://www.pornhub.com/',
}

def get_formats_aggressive(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'http_headers': HEADERS,
        'noplaylist': True,
        # This is key: it tells yt-dlp to allow HLS/m3u8 formats
        'check_formats': 'all', 
    }
    
    if os.path.exists(COOKIE_FILE):
        ydl_opts['cookiefile'] = COOKIE_FILE

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            if not info:
                return [], "Site blocked extraction."
            
            title = info.get('title', 'Video')
            formats = info.get('formats', [])
            valid_options = []
            
            for f in formats:
                height = f.get('height')
                # Include formats even if filesize is unknown (common for HLS)
                if height and height >= 240:
                    res_str = f"{height}p"
                    
                    # Calculate size if available
                    filesize = f.get('filesize') or f.get('filesize_approx') or 0
                    size_label = f"{round(filesize / (1024*1024), 1)}MB" if filesize else "Link (HLS)"
                    
                    # Only add the best version for each resolution
                    if not any(opt['res'] == res_str for opt in valid_options):
                        valid_options.append({
                            'res': res_str, 
                            'id': f['format_id'], 
                            'size': size_label
                        })
            
            return sorted(valid_options, key=lambda x: int(x['res'][:-1]), reverse=True), title
        except Exception as e:
            return [], str(e)

# --- Handlers ---

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await client.set_bot_commands([
        BotCommand("start", "Restart"),
        BotCommand("status", "Check Storage/Cookies")
    ])
    await message.reply_text("✅ **Singapore Node Active.**\nSend a link to extract.")

@app.on_message(filters.command("status") & filters.private)
async def status_cmd(client, message):
    _, _, free = shutil.disk_usage("/")
    c_exists = "✅ Active" if os.path.exists(COOKIE_FILE) else "❌ Missing"
    await message.reply_text(f"📊 **Status**\nDisk Free: {free // (2**30)}GB\nCookies: {c_exists}")

@app.on_message(filters.document & filters.private)
async def save_cookies(client, message):
    if message.document.file_name == "cookies.txt":
        await message.download(file_name=COOKIE_FILE)
        await message.reply_text("✅ **Cookies Saved.**")

@app.on_message(filters.text & filters.private & ~filters.command(["start", "status"]))
async def handle_url(client, message):
    url = message.text
    if "http" not in url: return
    
    msg = await message.reply_text("⚡ **Extracting Manifests...**")
    qualities, title_data = get_formats_aggressive(url)

    if not qualities:
        return await msg.edit(f"❌ **No formats found.**\nError: `{title_data}`")

    user_data[message.from_user.id] = {"url": url, "title": title_data}
    buttons = [[InlineKeyboardButton(f"📥 {q['res']} ({q['size']})", callback_data=q['id'])] for q in qualities]
    
    await msg.edit(f"🎬 **{title_data[:50]}**", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query()
async def download_now(client, callback_query):
    f_id = callback_query.data
    uid = callback_query.from_user.id
    data = user_data.get(uid)
    
    file_path = f"{DOWNLOAD_PATH}/{uid}_{f_id}.mp4"
    await callback_query.message.edit("📥 **Downloading...**\n(Merging video/audio)")

    ydl_opts = {
        'format': f'{f_id}+bestaudio/best',
        'outtmpl': file_path,
        'merge_output_format': 'mp4',
        'http_headers': HEADERS,
        # Allow downloading from manifest links
        'allow_unplayable_formats': True, 
    }
    if os.path.exists(COOKIE_FILE):
        ydl_opts['cookiefile'] = COOKIE_FILE

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([data['url']]))

        await callback_query.message.edit("🚀 **Uploading to Telegram...**")
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
