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

# Импортируем функции из deezer.py (они уже умеют собирать все треки)
from deezer import get_album_tracks, search_artist_albums, search_album as deezer_search_album

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_THREAD_ID = os.getenv("TARGET_THREAD_ID")

HEADERS = {"User-Agent": "Mozilla/5.0"}

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "OK"

def run_web():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def clean_query(text: str):
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def format_duration(seconds: int):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02}:{secs:02}"
    return f"{minutes}:{secs:02}"

def parse_music_url(url: str):
    # Spotify через oembed
    if "spotify.com/album/" in url:
        resp = requests.get("https://open.spotify.com/oembed", params={"url": url}, timeout=10)
        if resp.status_code != 200:
            raise Exception("Spotify oembed failed")
        data = resp.json()
        title = data.get("title", "")
        author = data.get("author_name", "")
        if " - " in title:
            artist, album = title.split(" - ", 1)
        else:
            artist = author
            album = title
        return {
            "album_name": clean_query(album),
            "artists": clean_query(artist),
            "cover": data.get("thumbnail_url")
        }
    # Apple Music
    elif "music.apple.com" in url:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        title_tag = soup.find("title")
        if not title_tag:
            raise Exception("Apple Music title not found")
        title = title_tag.string.strip()
        title = title.replace(" - Apple Music", "")
        if " by " in title:
            album, artist = title.split(" by ", 1)
        else:
            album = title
            artist = ""
        return {
            "album_name": clean_query(album),
            "artists": clean_query(artist),
            "cover": None
        }
    raise Exception("Unsupported link")

def build_album_caption(album_info):
    tracklist = "\n".join(album_info["tracks"])
    caption = (
        f"🎵 {album_info['title']}\n\n"
        f"👥 {album_info['artist']}\n\n"
        f"📅 {album_info['release_date']}\n"
        f"💿 {album_info['track_count']} tracks\n"
        f"⏳ {album_info['duration']}\n\n"
        f"---Tracklist---\n\n"
        f"{tracklist}"
    )
    # Telegram ограничение 4096 символов, обрежем если нужно
    if len(caption) > 4000:
        # Оставляем место для сообщения об обрезке
        max_len = 4000 - len(caption) + len(tracklist) - 50
        truncated = tracklist[:max_len]
        caption = (
            f"🎵 {album_info['title']}\n\n"
            f"👥 {album_info['artist']}\n\n"
            f"📅 {album_info['release_date']}\n"
            f"💿 {album_info['track_count']} tracks\n"
            f"⏳ {album_info['duration']}\n\n"
            f"---Tracklist (first {max_len} chars)---\n\n"
            f"{truncated}\n\n... (tracklist truncated)"
        )
    return caption

def build_album_buttons(album_info):
    title = album_info["title"]
    artist = album_info["artist"]
    query = requests.utils.quote(f"{artist} {title}")
    keyboard = [
        [InlineKeyboardButton("Spotify", url=f"https://open.spotify.com/search/{query}"),
         InlineKeyboardButton("Apple Music", url=f"https://music.apple.com/us/search?term={query}")],
        [InlineKeyboardButton("Deezer", url=f"https://www.deezer.com/search/{query}"),
         InlineKeyboardButton("TIDAL", url=f"https://listen.tidal.com/search?q={query}")],
        [InlineKeyboardButton("YouTube", url=f"https://music.youtube.com/search?q={query}"),
         InlineKeyboardButton("SoundCloud", url=f"https://soundcloud.com/search?q={query}")],
        [InlineKeyboardButton("Other releases", callback_data=f"artist::{artist}")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def send_album(update, context, album_id):
    album_info = get_album_tracks(album_id)  # из deezer.py, собирает все треки
    caption = build_album_caption(album_info)
    buttons = build_album_buttons(album_info)
    img_resp = requests.get(album_info["cover"], timeout=15)
    image_bytes = BytesIO(img_resp.content)
    safe_name = re.sub(r'[\\/*?:"<>|]', "", album_info["title"])
    image_bytes.name = f"{safe_name}.jpg"

    target = None
    if hasattr(update, "callback_query") and update.callback_query:
        target = update.callback_query.message
    elif hasattr(update, "message") and update.message:
        target = update.message
    if not target:
        return

    kwargs = {}
    if TARGET_THREAD_ID and target.chat.type in ["group", "supergroup"]:
        kwargs["message_thread_id"] = int(TARGET_THREAD_ID)

    await target.reply_document(
        document=InputFile(image_bytes),
        caption=caption,
        reply_markup=buttons,
        **kwargs
    )

async def handle_artist_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    artist_name = query.data.replace("artist::", "")
    albums = search_artist_albums(artist_name)
    if not albums:
        await query.message.reply_text("Artist not found or no albums")
        return
    keyboard = [[InlineKeyboardButton(alb["title"], callback_data=f"album::{alb['id']}")] for alb in albums]
    await query.message.reply_text(f"{artist_name} albums:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_album_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    album_id = int(query.data.replace("album::", ""))
    await send_album(update, context, album_id)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    # Фильтр по thread
    if TARGET_THREAD_ID and update.message.chat.type in ["group", "supergroup"]:
        thread_id = getattr(update.message, "message_thread_id", None)
        if str(thread_id) != str(TARGET_THREAD_ID):
            return

    text = update.message.text.strip()
    try:
        # --- Прямая обработка Deezer ссылок (самый надёжный способ) ---
        if "deezer.com/album/" in text:
            match = re.search(r"/album/(\d+)", text)
            if match:
                album_id = int(match.group(1))
                await send_album(update, context, album_id)
                return
            else:
                await update.message.reply_text("Invalid Deezer album link")
                return

        # --- Обработка Spotify и Apple Music ссылок через парсинг ---
        if "spotify.com/album/" in text or "music.apple.com" in text:
            parsed = parse_music_url(text)
            album_name = parsed["album_name"]
            artists = parsed["artists"]
            # Пробуем разные варианты запроса
            search_queries = [
                f"{album_name} {artists}",
                album_name,
                f"{artists} {album_name}",
            ]
            album = None
            for q in search_queries:
                print(f"Trying Deezer search: {q}")
                album = deezer_search_album(q)  # из deezer.py
                if album:
                    break
            if not album:
                await update.message.reply_text("Album not found on Deezer")
                return
            await send_album(update, context, album["id"])
            return

        # --- Поиск по тексту (артист или альбом) ---
        # Сначала пробуем как исполнителя
        artist_albums = search_artist_albums(text)
        if artist_albums:
            keyboard = [[InlineKeyboardButton(alb["title"], callback_data=f"album::{alb['id']}")] for alb in artist_albums]
            await update.message.reply_text(f"Albums by {text}:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Пробуем как альбом
        album = deezer_search_album(text)
        if album:
            await send_album(update, context, album["id"])
            return

        await update.message.reply_text("Album not found")
    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text(f"Error: {str(e)}")

def main():
    asyncio.set_event_loop(asyncio.new_event_loop())
    web_thread = Thread(target=run_web, daemon=True)
    web_thread.start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_artist_buttons, pattern=r"^artist::"))
    app.add_handler(CallbackQueryHandler(handle_album_buttons, pattern=r"^album::"))
    print("Bot started.")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()