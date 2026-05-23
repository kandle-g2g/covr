import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from spotify_parser import extract_spotify_metadata
from deezer import search_album, get_album_tracks
from datetime import datetime
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_THREAD_ID = 12446

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    if chat_type in ["group", "supergroup"]:
        if update.message.message_thread_id != ALLOWED_THREAD_ID:
            return

    text = update.message.text.strip()
    if "spotify.com/album/" not in text:
        return

    try:
        # 1. Получаем метаданные из Spotify
        spotify_data = extract_spotify_metadata(text)

        # 2. Ищем альбом в Deezer
        album = search_album(spotify_data["album_name"], spotify_data["artists"])
        album_info = get_album_tracks(album["id"])

        # 3. Форматируем дату
        parsed_date = datetime.strptime(album_info["release_date"], "%Y-%m-%d")
        formatted_date = f"{parsed_date.strftime('%B')} {parsed_date.day}, {parsed_date.year}"

        # 4. Формируем треклист (все треки)
        tracks_text = "\n".join(album_info["tracks"])

        # 5. Полное сообщение
        message = (
            f"🎵 <b>{album_info['title']}</b>\n\n"
            f"👥 {album_info['artists']}\n\n"
            f"📅 {formatted_date}\n"
            f"💿 {album_info['tracks_count']} tracks\n"
            f"⏳ {album_info['total_duration']}\n\n"
            f"---Tracklist---\n\n"
            f"{tracks_text}"
        )

        # 6. Кнопки (Spotify, Deezer, Apple Music)
        # Универсальная ссылка на поиск в Apple Music
        search_term = f"{album_info['title']} {album_info['artists']}"
        apple_music_url = f"https://music.apple.com/us/search?term={search_term.replace(' ', '+')}"

        keyboard = [
            [
                InlineKeyboardButton("🎧 Spotify", url=text),
                InlineKeyboardButton("💿 Deezer", url=album["link"]),
                InlineKeyboardButton("🎵 Apple Music", url=apple_music_url)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # 7. Скачиваем обложку
        image_response = requests.get(album_info["cover"])
        safe_title = "".join(c for c in album_info["title"] if c.isalnum() or c in (" ", "-", "_")).rstrip()
        file_name = f"{safe_title}.jpg"
        with open(file_name, "wb") as f:
            f.write(image_response.content)

        # 8. Отправляем фото с подписью и кнопками
        with open(file_name, "rb") as image_file:
            await update.message.reply_document(
                document=image_file,
                caption=message,
                parse_mode="HTML",
                reply_markup=reply_markup
            )

        # 9. Удаляем временный файл
        os.remove(file_name)

    except Exception as e:
        await update.message.reply_text(f"Ошибка:\n{str(e)}")