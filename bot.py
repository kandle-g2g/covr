import os
import re
import asyncio
import requests
from io import BytesIO
from threading import Thread
from flask import Flask
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from music_parser import parse_music_url

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_THREAD_ID = os.getenv("TARGET_THREAD_ID")
HEADERS = {"User-Agent": "Mozilla/5.0"}

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "OK"

def run_web():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

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

# ------------------------------------
# Deezer API
# ------------------------------------
def deezer_search_album(query: str) -> dict | None:
    try:
        resp = requests.get("https://api.deezer.com/search/album", params={"q": query}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data["data"][0] if data.get("data") else None
    except Exception as e:
        print(f"Deezer search error: {e}")
    return None

def find_deezer_album_by_artist_and_title(album_name: str, artist_name: str) -> dict | None:
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

def extract_deezer_id(url: str) -> int | None:
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

# ------------------------------------
# Построение сообщения
# ------------------------------------
def build_album_caption(album_info: dict) -> str:
    tracklist = "\n".join(album_info["tracks"])
    # Форматирование даты
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

async def send_album(update, context, album_id: int):
    from deezer import get_album_tracks
    album_info = get_album_tracks(album_id)
    caption = build_album_caption(album_info)
    buttons = build_album_buttons(album_info)
    img_resp = requests.get(album_info["cover"], timeout=30)
    image_bytes = BytesIO(img_resp.content)
    safe_name = re.sub(r'[\\/*?:"<>|]', "", album_info["title"])
    image_bytes.name = f"{safe_name}.jpg"

    target = update.callback_query.message if update.callback_query else update.message
    if not target:
        return

    kwargs = {}
    if TARGET_THREAD_ID and target.chat.type in ["group", "supergroup"]:
        kwargs["message_thread_id"] = int(TARGET_THREAD_ID)

    await target.reply_document(
        document=InputFile(image_bytes),
        caption=caption,
        reply_markup=buttons,
        read_timeout=60,
        write_timeout=60,
        **kwargs
    )

# ------------------------------------
# Обработчики
# ------------------------------------
async def handle_artist_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    artist_name = query.data.replace("artist::", "")
    from deezer import search_artist_albums
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
    await send_album(update, context, album_id)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if TARGET_THREAD_ID and update.message.chat.type in ["group", "supergroup"]:
        thread_id = getattr(update.message, "message_thread_id", None)
        if str(thread_id) != str(TARGET_THREAD_ID):
            return

    text = update.message.text.strip()
    print(f"📩 Received: {text}")

    try:
        # 1. Deezer ссылка
        if "deezer.com" in text and "/album/" in text:
            deezer_id = extract_deezer_id(text)
            if deezer_id:
                print(f"✅ Deezer direct ID: {deezer_id}")
                await send_album(update, context, deezer_id)
                return

        # 2. Spotify ссылка
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

        # 3. Apple Music ссылка
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
                else:
                    print("❌ Album not found in Deezer for Apple Music link")

        # 4. Текстовый поиск: сначала альбом
        album = deezer_search_album(text)
        if album:
            await send_album(update, context, album["id"])
            return

        # 5. Если альбом не найден, ищем артиста
        from deezer import search_artist_albums
        artist_albums = search_artist_albums(text)
        if artist_albums:
            keyboard = [[InlineKeyboardButton(alb["title"], callback_data=f"album::{alb['id']}")] for alb in artist_albums]
            await update.message.reply_text(f"🎤 {text} albums:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        await update.message.reply_text("❌ Album not found")
    except Exception as e:
        print(f"🔥 Error: {e}")
        await update.message.reply_text(f"Error: {str(e)}")

def main():
    asyncio.set_event_loop(asyncio.new_event_loop())
    web_thread = Thread(target=run_web, daemon=True)
    web_thread.start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_artist_buttons, pattern=r"^artist::"))
    app.add_handler(CallbackQueryHandler(handle_album_buttons, pattern=r"^album::"))
    print("✅ Bot started")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()