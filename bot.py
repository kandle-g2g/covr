import os
import re
import requests

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters
)

from deezer import search_album
from spotify_parser import extract_album_name


BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID нужной подтемы
ALLOWED_THREAD_ID = 2


def format_duration(seconds):

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02}:{secs:02}"

    return f"{minutes:02}:{secs:02}"


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    # Работа в ЛС + фильтр подтемы
    chat_type = update.effective_chat.type

    if chat_type in ["group", "supergroup"]:

        if (
            update.message.message_thread_id
            != ALLOWED_THREAD_ID
        ):
            return

    text = update.message.text

    if not text:
        return

    spotify_match = re.search(
        r"(https?://open\.spotify\.com/album/[^\s]+)",
        text
    )

    if not spotify_match:
        return

    spotify_url = spotify_match.group(1)

    try:

        album_name = extract_album_name(
            spotify_url
        )

        album = search_album(
            album_name
        )

        if not album:

            await update.message.reply_text(
                "Album not found."
            )

            return

        title = album["title"]

        artists = ", ".join(
            artist["name"]
            for artist in album["contributors"]
        )

        release_date = album["release_date"]

        year, month, day = release_date.split("-")

        months = {
            "01": "January",
            "02": "February",
            "03": "March",
            "04": "April",
            "05": "May",
            "06": "June",
            "07": "July",
            "08": "August",
            "09": "September",
            "10": "October",
            "11": "November",
            "12": "December"
        }

        release_date = (
            f"{months[month]} "
            f"{int(day)}, "
            f"{year}"
        )

        tracks = album["full_tracks"]

        track_count = len(tracks)

        total_duration = sum(
            track["duration"]
            for track in tracks
        )

        album_duration = format_duration(
            total_duration
        )

        tracklist = "\n".join(
            track["title"]
            for track in tracks
        )

        message = (
            f"🎵 {title}\n\n"
            f"👥 {artists}\n\n"
            f"📅 {release_date}\n"
            f"💿 {track_count} tracks\n"
            f"⏱ {album_duration}\n\n"
            f"{tracklist}"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "Spotify",
                    url=spotify_url
                ),
                InlineKeyboardButton(
                    "Deezer",
                    url=album["link"]
                )
            ]
        ])

        # Получаем оригинальную обложку
        image_response = requests.get(
            album["cover_xl"]
        )

        image_bytes = image_response.content

        # Отправляем как файл
        await update.message.reply_document(
            document=image_bytes,
            filename=f"{title}.jpg",
            caption=message,
            reply_markup=keyboard
        )

    except Exception as e:

        print(e)

        await update.message.reply_text(
            f"Error:\n{e}"
        )


def main():

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("Бот запущен")

    app.run_polling()


if __name__ == "__main__":
    main()