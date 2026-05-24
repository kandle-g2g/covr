import os
import re
import threading
import requests
from io import BytesIO
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from music_parser import parse_music_url
from deezer import get_album_tracks, search_artist_albums, search_artist

# ---------- Конфигурация ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_THREAD_ID = os.getenv("TARGET_THREAD_ID")
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ---------- Flask для healthcheck ----------
flask_app = Flask(__name__)

@flask_app.route("/healthcheck")
def healthcheck():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# ---------- Вспомогательные функции ----------
def clean_query(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[\u200e\u200f\u202a-\u202e]', '', text)
    text = re.sub(r"[\(\[].*?[\)\]]", "", text)
    text = re.sub(r"\b(Album|Single|EP|Deluxe|Edition|Remastered)\b", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02}:{secs:02}"
    return f"{minutes}:{secs:02}"

# ---------- Deezer API ----------
def deezer_search_album(query: str):
    try:
        resp = requests.get("https://api.deezer.com/search/album", params={"q": query}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data["data"][0] if data.get("data") else None
    except Exception as e:
        print(f"Deezer search error: {e}")
    return None

def find_deezer_album_by_artist_and_title(album_name: str, artist_name: str):
    album_clean = clean_query(album_name)
    artist_clean = clean_query(artist_name)
    queries = [
        f"{album_clean} {artist_clean}",
        f"{artist_clean} {album_clean}",
        album_clean,
        f'"{album_clean}"',
        f"{artist_clean} \"{album_clean}\""
    ]
    for q in queries:
        print(f"🔎 Searching Deezer: {q}")
        album = deezer_search_album(q)
        if album:
            deezer_artist = album.get("artist", {}).get("name", "").lower()
            if artist_clean.lower() in deezer_artist or deezer_artist in artist_clean.lower():
                print(f"✅ Found: {album['title']} by {album['artist']['name']}")
                return album
            if q == album_clean:
                print(f"⚠️ Accepted by title only: {album['title']}")
                return album
    return None

def extract_deezer_id(url: str):
    if "deezer.com" not in url:
        return None
    m = re.search(r"/album[/]?(\d+)", url)
    if m:
        return int(m.group(1))
    if "deezer.page.link" in url:
        try:
            resp = requests.head(url, allow_redirects=True, timeout=10)
            final = resp.url
            m2 = re.search(r"/album[/]?(\d+)", final)
            if m2:
                return int(m2.group(1))
        except:
            pass
    return None

# ---------- Построение сообщения ----------
def build_album_caption(album_info: dict) -> str:
    tracklist = "\n".join(album_info["tracks"])
    raw_date = album_info.get("release_date", "")
    formatted_date = raw_date
    try:
        from datetime import datetime
        dt = datetime.strptime(raw_date, "%Y-%m-%d")
        formatted_date = dt.strftime("%B %d, %Y")
    except:
        pass
    caption = (
        f"🎵 {album_info['title']}\n\n"
        f"👥 {album_info['artist']}\n\n"
        f"📅 {formatted_date}\n"
        f"💿 {album_info['track_count']} tracks\n"
        f"⏳ {album_info['duration']}\n\n"
        f"---Tracklist---\n\n"
        f"{tracklist}"
    )
    if len(caption) > 4000:
        max_len = 4000 - len(caption) + len(tracklist) - 50
        truncated = tracklist[:max_len]
        caption = (
            f"🎵 {album_info['title']}\n\n"
            f"👥 {album_info['artist']}\n\n"
            f"📅 {formatted_date}\n"
            f"💿 {album_info['track_count']} tracks\n"
            f"⏳ {album_info['duration']}\n\n"
            f"---Tracklist (first {max_len} chars)---\n\n"
            f"{truncated}\n\n... (tracklist truncated)"
        )
    return caption

def build_album_buttons(album_info: dict) -> InlineKeyboardMarkup:
    title = album_info["title"]
    artist = album_info["artist"]
    query = requests.utils.quote(f"{artist} {title}")
    keyboard = [
        [InlineKeyboardButton("🎧 Spotify", url=f"https://open.spotify.com/search/{query}"),
         InlineKeyboardButton("🍎 Apple Music", url=f"https://music.apple.com/us/search?term={query}")],
        [InlineKeyboardButton("💿 Deezer", url=f"https://www.deezer.com/search/{query}"),
         InlineKeyboardButton("🎶 TIDAL", url=f"https://listen.tidal.com/search?q={query}")],
        [InlineKeyboardButton("📺 YouTube", url=f"https://music.youtube.com/search?q={query}"),
         InlineKeyboardButton("☁️ SoundCloud", url=f"https://soundcloud.com/search?q={query}")],
        [InlineKeyboardButton("🎤 Other releases", callback_data=f"artist::{artist}")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def send_album(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id: int):
    print(f"📤 send_album called with album_id={album_id}")
    try:
        album_info = get_album_tracks(album_id)
        print(f"✅ Got album: {album_info['title']} ({album_info['track_count']} tracks)")
    except Exception as e:
        print(f"❌ Error fetching album: {e}")
        await update.message.reply_text("Error fetching album from Deezer")
        return

    caption = build_album_caption(album_info)
    buttons = build_album_buttons(album_info)

    try:
        img_resp = requests.get(album_info["cover"], timeout=30)
        print(f"🖼 Cover downloaded, size={len(img_resp.content)}")
    except Exception as e:
        print(f"❌ Cover download error: {e}")
        await update.message.reply_text("Error downloading cover")
        return

    image_bytes = BytesIO(img_resp.content)
    safe_name = re.sub(r'[\\/*?:"<>|]', "", album_info["title"])
    image_bytes.name = f"{safe_name}.jpg"

    target = update.callback_query.message if update.callback_query else update.message
    if not target:
        print("❌ No target message")
        return

    kwargs = {}
    if TARGET_THREAD_ID and target.chat.type in ["group", "supergroup"]:
        kwargs["message_thread_id"] = int(TARGET_THREAD_ID)
        print(f"🧵 thread_id={kwargs['message_thread_id']}")

    print("📤 Sending document...")
    try:
        await target.reply_document(
            document=InputFile(image_bytes),
            caption=caption,
            reply_markup=buttons,
            read_timeout=60,
            write_timeout=60,
            **kwargs
        )
        print("✅ Document sent")
    except Exception as e:
        print(f"❌ Send failed: {e}")
        await update.message.reply_text(f"Error sending album: {e}")

# ---------- Обработчики команд ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 *Music Album Bot*\n\n"
        "Send me:\n"
        "• an album name (e.g., *Graduation*)\n"
        "• an artist name (e.g., *Kanye West*) – I'll show their albums\n"
        "• a link from Spotify, Apple Music, or Deezer\n\n"
        "Or use /artist <name> to search for an artist explicitly.\n\n"
        "_Bot is awake and listening!_",
        parse_mode="Markdown"
    )

async def artist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /artist <artist name>")
        return
    artist_name = " ".join(context.args)
    print(f"🎤 /artist command: {artist_name}")
    albums = search_artist_albums(artist_name)
    if not albums:
        await update.message.reply_text(f"No albums found for {artist_name}")
        return
    keyboard = [[InlineKeyboardButton(alb["title"], callback_data=f"album::{alb['id']}")] for alb in albums]
    await update.message.reply_text(f"🎤 {artist_name} albums:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_artist_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    artist_name = query.data.replace("artist::", "")
    print(f"🎤 Artist button: {artist_name}")
    albums = search_artist_albums(artist_name)
    if not albums:
        await query.message.reply_text("Artist not found")
        return
    keyboard = [[InlineKeyboardButton(alb["title"], callback_data=f"album::{alb['id']}")] for alb in albums]
    await query.message.reply_text(f"🎤 {artist_name} albums:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_album_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    album_id = int(query.data.replace("album::", ""))
    print(f"💿 Album button: {album_id}")
    await send_album(update, context, album_id)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if TARGET_THREAD_ID and update.message.chat.type in ["group", "supergroup"]:
        thread_id = getattr(update.message, "message_thread_id", None)
        if str(thread_id) != str(TARGET_THREAD_ID):
            print(f"⏩ Ignored thread {thread_id} (expected {TARGET_THREAD_ID})")
            return

    text = update.message.text.strip()
    print(f"📩 Received: {text}")

    try:
        # ----- Ссылки -----
        if "deezer.com" in text and "/album/" in text:
            deezer_id = extract_deezer_id(text)
            if deezer_id:
                print(f"✅ Deezer ID: {deezer_id}")
                await send_album(update, context, deezer_id)
                return
        if "spotify.com/album/" in text:
            parsed = parse_music_url(text)
            if parsed:
                album_name = clean_query(parsed["album_name"])
                artists = clean_query(parsed["artists"])
                print(f"🎵 Spotify: album='{album_name}', artist='{artists}'")
                album = find_deezer_album_by_artist_and_title(album_name, artists)
                if album:
                    await send_album(update, context, album["id"])
                    return
        if "music.apple.com" in text:
            parsed = parse_music_url(text)
            if parsed:
                album_name = clean_query(parsed["album_name"])
                artists = clean_query(parsed["artists"])
                print(f"🍎 Apple Music: album='{album_name}', artist='{artists}'")
                album = find_deezer_album_by_artist_and_title(album_name, artists)
                if album:
                    await send_album(update, context, album["id"])
                    return

        # ----- Текстовый поиск: сначала альбом -----
        album = deezer_search_album(text)
        if album:
            print(f"📀 Album found: {album['title']}")
            await send_album(update, context, album["id"])
            return

        # ----- Если не найден альбом, то артист -----
        artist_obj = search_artist(text)
        if artist_obj:
            albums = search_artist_albums(text)
            if albums:
                keyboard = [[InlineKeyboardButton(alb["title"], callback_data=f"album::{alb['id']}")] for alb in albums]
                await update.message.reply_text(f"🎤 {artist_obj['name']} albums:", reply_markup=InlineKeyboardMarkup(keyboard))
                return

        await update.message.reply_text("❌ Album or artist not found. Try /artist <name>.")
    except Exception as e:
        print(f"🔥 Error in handle_message: {e}")
        await update.message.reply_text(f"Internal error: {e}")

# ---------- Запуск ----------
def run_polling():
    # Удаляем вебхук на случай, если он был установлен
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        print("✅ Webhook deleted")
    except Exception as e:
        print(f"Failed to delete webhook: {e}")

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("artist", artist_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_artist_buttons, pattern=r"^artist::"))
    application.add_handler(CallbackQueryHandler(handle_album_buttons, pattern=r"^album::"))

    print("✅ Бот запущен в режиме polling, слушаем сообщения...")
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Запускаем Flask-сервер в фоновом потоке (для healthcheck)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    # Запускаем polling в основном потоке
    run_polling()