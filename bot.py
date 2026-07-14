import os
import re
import time
import threading
import requests
from io import BytesIO
from flask import Flask
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Импортируйте ваши модули (пути должны быть правильные)
from music_parser import parse_music_url
from deezer import get_album_tracks, search_artist_albums, search_artist

# ---------- Конфигурация ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")   # например, "MyAwesomeBot" (без @)
TARGET_THREAD_ID = os.getenv("TARGET_THREAD_ID")
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ---------- Flask для healthcheck ----------
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot is running"

@flask_app.route("/health")
def health():
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

# ---------- Построение сообщения в HTML с гиперссылками ----------
def build_album_caption(album_info: dict, simple: bool = False) -> str:
    if simple:
        caption = f"🎵 <b>{album_info['title']}</b>\n\n👥 {album_info['artist']}"
    else:
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
            f"🎵 <b>{album_info['title']}</b>\n\n"
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
                f"🎵 <b>{album_info['title']}</b>\n\n"
                f"👥 {album_info['artist']}\n\n"
                f"📅 {formatted_date}\n"
                f"💿 {album_info['track_count']} tracks\n"
                f"⏳ {album_info['duration']}\n\n"
                f"---Tracklist (first {max_len} chars)---\n\n"
                f"{truncated}\n\n... (tracklist truncated)"
            )

    title = album_info["title"]
    artist = album_info["artist"]
    query = requests.utils.quote(f"{artist} {title}")
    artist_query = requests.utils.quote(artist)

    # Ссылка "Other releases" – deep link на бота (работает в HTML)
    if BOT_USERNAME:
        other_link = f"https://t.me/{BOT_USERNAME}?start=artist_{artist_query}"
        other_text = f'🎤 <a href="{other_link}">Other releases of {artist}</a>'
    else:
        other_text = f'🎤 <a href="https://www.deezer.com/search/artist?q={artist_query}">Other releases of {artist} on Deezer</a>'

    # Все ссылки в HTML
    links = (
        f"\n\n🎧 <a href=\"https://open.spotify.com/search/{query}\">Spotify</a> | 🍎 <a href=\"https://music.apple.com/us/search?term={query}\">Apple Music</a>\n"
        f"💿 <a href=\"https://www.deezer.com/search/{query}\">Deezer</a> | 🎶 <a href=\"https://listen.tidal.com/search?q={query}\">TIDAL</a>\n"
        f"📺 <a href=\"https://music.youtube.com/search?q={query}\">YouTube</a> | ☁️ <a href=\"https://soundcloud.com/search?q={query}\">SoundCloud</a>\n"
        f"{other_text}"
    )
    caption += links
    return caption

async def send_album(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id: int):
    target = update.callback_query.message if update.callback_query else update.message
    if not target:
        print("❌ No target message")
        return

    print(f"📤 send_album called with album_id={album_id}")
    try:
        album_info = get_album_tracks(album_id)
        print(f"✅ Got album: {album_info['title']} ({album_info['track_count']} tracks)")
    except Exception as e:
        print(f"❌ Error fetching album: {e}")
        await target.reply_text("Error fetching album from Deezer")
        return

    simple_mode = context.chat_data.get('simple_mode', False)
    caption = build_album_caption(album_info, simple_mode)

    try:
        img_resp = requests.get(album_info["cover"], timeout=30)
        print(f"🖼 Cover downloaded, size={len(img_resp.content)}")
    except Exception as e:
        print(f"❌ Cover download error: {e}")
        await target.reply_text("Error downloading cover")
        return

    image_bytes = BytesIO(img_resp.content)
    safe_name = re.sub(r'[\\/*?:"<>|]', "", album_info["title"])
    image_bytes.name = f"{safe_name}.jpg"

    kwargs = {}
    if TARGET_THREAD_ID and target.chat.type in ["group", "supergroup"]:
        kwargs["message_thread_id"] = int(TARGET_THREAD_ID)
        print(f"🧵 thread_id={kwargs['message_thread_id']}")

    print("📤 Sending...")
    try:
        if simple_mode:
            await target.reply_photo(
                photo=InputFile(image_bytes),
                caption=caption,
                parse_mode="HTML",   # используем HTML
                read_timeout=60,
                write_timeout=60,
                **kwargs
            )
            print("✅ Photo sent (simple mode)")
        else:
            await target.reply_document(
                document=InputFile(image_bytes),
                caption=caption,
                parse_mode="HTML",   # используем HTML
                read_timeout=60,
                write_timeout=60,
                **kwargs
            )
            print("✅ Document sent (full mode)")
    except Exception as e:
        print(f"❌ Send failed: {e}")
        await target.reply_text(f"Error sending album: {e}")

# ---------- Обработчики команд ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем deep linking параметр
    if context.args:
        payload = context.args[0]
        if payload.startswith("artist_"):
            artist_query = payload.replace("artist_", "")
            artist_name = requests.utils.unquote(artist_query)
            print(f"🎤 Deep link artist: {artist_name}")
            albums = search_artist_albums(artist_name)
            if not albums:
                await update.message.reply_text(f"No albums found for {artist_name}")
                return
            keyboard = [[InlineKeyboardButton(alb["title"], callback_data=f"album::{alb['id']}")] for alb in albums]
            await update.message.reply_text(f"🎤 {artist_name} albums:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

    # Обычный /start без параметра
    await update.message.reply_text(
        "🎵 <b>Covr bot</b>\n\n"
        "Send me:\n"
        "• an album name (e.g., <i>Graduation</i>)\n"
        "• an artist name (e.g., <i>Kanye West</i>) – I'll show their albums\n"
        "• a link from Spotify, Apple Music, or Deezer\n\n"
        "Or use /artist &lt;name&gt; to search for an artist explicitly.\n\n"
        "Commands:\n"
        "/simple – show only cover (as photo), title and artist\n"
        "/full   – show full info (cover as file, tracklist, duration, etc.)\n\n"
        "All links are embedded in the message and will stay when forwarded.\n"
        "The 'Other releases' link will open a chat with the bot and automatically show the artist's albums.\n\n"
        "<i>Bot is awake and listening!</i>",
        parse_mode="HTML"
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

async def simple_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data['simple_mode'] = True
    await update.message.reply_text("✅ Simple mode enabled. Only cover (as photo), title and artist will be shown.")

async def full_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data['simple_mode'] = False
    await update.message.reply_text("✅ Full mode enabled. All info (tracklist, duration, cover as file) will be shown.")

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

# ---------- Запуск polling с автоматическим перезапуском ----------
def run_polling_with_retry():
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        print("✅ Webhook deleted")
    except Exception as e:
        print(f"Failed to delete webhook: {e}")

    while True:
        try:
            application = Application.builder().token(BOT_TOKEN).build()
            application.add_handler(CommandHandler("start", start))
            application.add_handler(CommandHandler("artist", artist_command))
            application.add_handler(CommandHandler("simple", simple_command))
            application.add_handler(CommandHandler("full", full_command))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            application.add_handler(CallbackQueryHandler(handle_artist_buttons, pattern=r"^artist::"))
            application.add_handler(CallbackQueryHandler(handle_album_buttons, pattern=r"^album::"))

            print("✅ Бот запущен в режиме polling, слушаем сообщения...")
            application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            print(f"❌ Polling упал с ошибкой: {e}. Перезапуск через 10 секунд...")
            time.sleep(10)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    run_polling_with_retry()