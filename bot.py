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

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_THREAD_ID = os.getenv("TARGET_THREAD_ID")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "OK"

def run_web():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def clean_query(text: str) -> str:
    """Очищает текст от скобок, лишних пробелов и слов 'Album', 'Spotify' и т.п."""
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\[.*?\]", "", text)
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

# ---------------------- Deezer API helpers ----------------------
def deezer_search_album(query: str) -> dict | None:
    """Прямой поиск альбома в Deezer по текстовому запросу."""
    try:
        resp = requests.get("https://api.deezer.com/search/album", params={"q": query}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data["data"][0] if data.get("data") else None
    except Exception as e:
        print(f"Deezer search error: {e}")
    return None

def find_deezer_album_by_artist_and_title(album_name: str, artist_name: str) -> dict | None:
    """Пытается найти альбом в Deezer, перебирая разные варианты запроса."""
    album_clean = clean_query(album_name)
    artist_clean = clean_query(artist_name)
    queries = [
        f"{album_clean} {artist_clean}",
        f"{artist_clean} {album_clean}",
        album_clean,
        f"\"{album_clean}\"",          # точное совпадение названия
        f"{artist_clean} \"{album_clean}\""
    ]
    for q in queries:
        print(f"🔎 Searching Deezer: {q}")
        album = deezer_search_album(q)
        if album:
            # Дополнительная проверка: совпадает ли исполнитель хотя бы частично?
            deezer_artist = album.get("artist", {}).get("name", "").lower()
            if artist_clean.lower() in deezer_artist or deezer_artist in artist_clean.lower():
                print(f"✅ Found: {album['title']} by {album['artist']['name']}")
                return album
            # Если не совпадает, но запрос был только по названию — всё равно возьмём
            if q == album_clean:
                print(f"⚠️ Partial match (title only): {album['title']}")
                return album
    return None

# ---------------------- Парсинг ссылок ----------------------
def extract_deezer_id_from_url(url: str) -> int | None:
    """Извлекает Deezer album ID из любой ссылки."""
    # Прямой ID в URL
    match = re.search(r"/album[/]?(\d+)", url)
    if match:
        return int(match.group(1))
    # Обработка deezer.page.link (редирект)
    if "deezer.page.link" in url:
        try:
            resp = requests.head(url, allow_redirects=True, timeout=10)
            final_url = resp.url
            match = re.search(r"/album[/]?(\d+)", final_url)
            if match:
                return int(match.group(1))
        except:
            pass
    return None

def parse_spotify_url(url: str) -> tuple[str, str] | None:
    """Возвращает (album_name, artist_name) из Spotify ссылки через oembed."""
    try:
        resp = requests.get("https://open.spotify.com/oembed", params={"url": url}, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        title = data.get("title", "")
        author = data.get("author_name", "")
        if " - " in title:
            artist, album = title.split(" - ", 1)
        else:
            artist = author
            album = title
        return clean_query(album), clean_query(artist)
    except Exception as e:
        print(f"Spotify parse error: {e}")
        return None

def parse_apple_url(url: str) -> tuple[str, str] | None:
    """Возвращает (album_name, artist_name) из Apple Music ссылки через парсинг HTML."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Пробуем взять og:title
        og_title = soup.find("meta", property="og:title")
        title_text = og_title["content"] if og_title else None
        if not title_text:
            title_tag = soup.find("title")
            if title_tag:
                title_text = title_tag.string
        if not title_text:
            return None
        # Очистка
        title_text = re.sub(r"\s*[-|]\s*Apple Music$", "", title_text, flags=re.I)
        if " by " in title_text:
            album, artist = title_text.split(" by ", 1)
        elif " – " in title_text:
            album, artist = title_text.split(" – ", 1)
        else:
            # fallback
            album = title_text
            artist = ""
        # Удаляем лишние слова
        album = re.sub(r"\b(Album|Deluxe|Edition|Remastered)\b", "", album, flags=re.I)
        return clean_query(album), clean_query(artist)
    except Exception as e:
        print(f"Apple Music parse error: {e}")
        return None

# ---------------------- Формирование сообщения ----------------------
def build_album_caption(album_info: dict) -> str:
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
    # Telegram limit 4096 symbols
    if len(caption) > 4000:
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

# ---------------------- Отправка альбома ----------------------
async def send_album(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id: int):
    from deezer import get_album_tracks   # импортируем здесь, чтобы избежать циклических зависимостей
    try:
        album_info = get_album_tracks(album_id)
    except Exception as e:
        print(f"Error fetching album {album_id}: {e}")
        raise
    caption = build_album_caption(album_info)
    buttons = build_album_buttons(album_info)
    img_resp = requests.get(album_info["cover"], timeout=15)
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
        **kwargs
    )

# ---------------------- Обработчики ----------------------
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
    # Фильтр по теме
    if TARGET_THREAD_ID and update.message.chat.type in ["group", "supergroup"]:
        thread_id = getattr(update.message, "message_thread_id", None)
        if str(thread_id) != str(TARGET_THREAD_ID):
            return

    text = update.message.text.strip()
    print(f"📩 Получено: {text}")

    try:
        # ----- 1. Deezer ссылка -----
        deezer_id = extract_deezer_id_from_url(text)
        if deezer_id:
            print(f"✅ Deezer ID found: {deezer_id}")
            await send_album(update, context, deezer_id)
            return

        # ----- 2. Spotify ссылка -----
        if "spotify.com/album/" in text:
            parsed = parse_spotify_url(text)
            if parsed:
                album_name, artist_name = parsed
                print(f"🎵 Spotify: album='{album_name}', artist='{artist_name}'")
                album = find_deezer_album_by_artist_and_title(album_name, artist_name)
                if album:
                    await send_album(update, context, album["id"])
                    return

        # ----- 3. Apple Music ссылка -----
        if "music.apple.com" in text:
            parsed = parse_apple_url(text)
            if parsed:
                album_name, artist_name = parsed
                print(f"🍎 Apple Music: album='{album_name}', artist='{artist_name}'")
                album = find_deezer_album_by_artist_and_title(album_name, artist_name)
                if album:
                    await send_album(update, context, album["id"])
                    return

        # ----- 4. Текстовый поиск (артист или альбом) -----
        # Сначала как исполнитель
        from deezer import search_artist_albums
        artist_albums = search_artist_albums(text)
        if artist_albums:
            keyboard = [[InlineKeyboardButton(alb["title"], callback_data=f"album::{alb['id']}")] for alb in artist_albums]
            await update.message.reply_text(f"🎤 {text} albums:", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        # Затем как альбом
        album = deezer_search_album(text)
        if album:
            await send_album(update, context, album["id"])
            return

        await update.message.reply_text("❌ Album not found")
    except Exception as e:
        print(f"Ошибка: {e}")
        await update.message.reply_text(f"Ошибка: {str(e)}")

def main():
    asyncio.set_event_loop(asyncio.new_event_loop())
    web_thread = Thread(target=run_web, daemon=True)
    web_thread.start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_artist_buttons, pattern=r"^artist::"))
    app.add_handler(CallbackQueryHandler(handle_album_buttons, pattern=r"^album::"))
    print("✅ Бот запущен и слушает сообщения")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()