import os
import asyncio
import yt_dlp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- Configuration ---
TOKEN = os.getenv("TELEGRAM_TOKEN")  # Set this in Railway Variables
MAX_SIZE_MB = 500
DOWNLOAD_PATH = "downloads"

if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# --- yt-dlp Functions ---
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
                # Filter: Must be video, under MAX_SIZE, and have a resolution
                if 0 < filesize <= (MAX_SIZE_MB * 1024 * 1024) and height:
                    size_str = f"{round(filesize / (1024 * 1024), 1)}MB"
                    res_str = f"{height}p"
                    if not any(opt['res'] == res_str for opt in valid_options):
                        valid_options.append({'res': res_str, 'id': f['format_id'], 'size': size_str})
            
            return sorted(valid_options, key=lambda x: int(x['res'][:-1]), reverse=True), info.get('title')
        except Exception as e:
            print(f"Error fetching formats: {e}")
            return [], None

# --- Telegram Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send me a video link to start downloading!")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "http" not in url:
        return

    msg = await update.message.reply_text("Checking video qualities...")
    qualities, title = get_formats(url)

    if not qualities:
        await msg.edit_text("❌ No formats found under 500MB or link is unsupported.")
        return

    context.user_data['url'] = url
    context.user_data['title'] = title

    keyboard = [
        [InlineKeyboardButton(f"{q['res']} ({q['size']})", callback_data=q['id'])] 
        for q in qualities
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await msg.edit_text(f"🎬 **{title}**\n\nChoose your preferred quality:", reply_markup=reply_markup, parse_mode="Markdown")

async def download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    format_id = query.data
    url = context.user_data.get('url')
    title = context.user_data.get('title', 'video')
    
    file_name = f"{DOWNLOAD_PATH}/{query.from_user.id}_{format_id}.mp4"
    await query.edit_message_text(f"⏳ Downloading {title}... This may take a minute.")

    ydl_opts = {
        'format': f'{format_id}+bestaudio/best',
        'outtmpl': file_name,
        'merge_output_format': 'mp4',
        'quiet': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        await query.edit_message_text("🚀 Uploading to Telegram...")
        
        with open(file_name, 'rb') as video:
            await context.bot.send_video(
                chat_id=query.message.chat_id,
                video=video,
                caption=f"✅ {title}",
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120
            )
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")
    finally:
        # Crucial for Railway: Delete the file after sending to save space
        if os.path.exists(file_name):
            os.remove(file_name)

# --- Main Runner ---
def main():
    # Increased timeouts for larger files
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(CallbackQueryHandler(download_callback))

    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
