import os

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)

from spotify_parser import (
    extract_spotify_metadata
)

from deezer import (
    search_album,
    get_album_tracks
)

from datetime import datetime

import requests


# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.getenv(
    "BOT_TOKEN"
)

# ID нужной подтемы (topic/thread)
ALLOWED_THREAD_ID = 12446


# =========================
# HANDLER
# =========================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    # Игнорируем сообщения вне нужной подтемы
    if (
        update.message.message_thread_id
        != ALLOWED_THREAD_ID
    ):
        return

    text = update.message.text.strip()

    # Игнорируем всё кроме Spotify album links
    if "spotify.com/album/" not in text:
        return

    try:

        # =========================
        # Spotify metadata
        # =========================

        spotify_data = (
            extract_spotify_metadata(
                text
            )
        )

        # =========================
        # Deezer search
        # =========================

        album = search_album(
            spotify_data["album_name"],
            spotify_data["artists"]
        )

        album_info = get_album_tracks(
            album["id"]
        )

        # =========================
        # Date formatting
        # =========================

        parsed_date = datetime.strptime(
            album_info["release_date"],
            "%Y-%m-%d"
        )

        formatted_date = (
            f"{parsed_date.strftime('%B')} "
            f"{parsed_date.day}, "
            f"{parsed_date.year}"
        )

        # =========================
        # Tracklist
        # =========================

        tracks_text = "\n".join(
            album_info["tracks"]
        )

        # =========================
        # Message
        # =========================

        message = (
            f"🎵 <b>{album_info['title']}</b>\n\n"
            f"👥 {album_info['artists']}\n\n"
            f"📅 {formatted_date}\n"
            f"💿 {album_info['tracks_count']} tracks\n"
            f"⏳ {album_info['total_duration']}\n\n"
            f"{tracks_text}"
        )

        # =========================
        # Buttons
        # =========================

        keyboard = [
            [
                InlineKeyboardButton(
                    "🎧 Spotify",
                    url=text
                ),

                InlineKeyboardButton(
                    "💿 Deezer",
                    url=album["link"]
                )
            ]
        ]

        reply_markup = (
            InlineKeyboardMarkup(
                keyboard
            )
        )

        # =========================
        # Download cover
        # =========================

        image_response = requests.get(
            album_info["cover"]
        )

        # Safe filename
        safe_title = "".join(
            c for c in album_info["title"]
            if (
                c.isalnum()
                or c in (
                    " ",
                    "-",
                    "_"
                )
            )
        ).rstrip()

        file_name = (
            f"{safe_title}.jpg"
        )

        with open(file_name, "wb") as f:

            f.write(
                image_response.content
            )

        # =========================
        # Send image
        # =========================

        with open(file_name, "rb") as image_file:

            await update.message.reply_document(
                document=image_file,
                caption=message,
                parse_mode="HTML",
                reply_markup=reply_markup
            )

        # =========================
        # Remove temp file
        # =========================

        os.remove(file_name)

    except Exception as e:

        await update.message.reply_text(
            f"Ошибка:\n{str(e)}"
        )


# =========================
# MAIN
# =========================

def main():

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT,
            handle_message
        )
    )

    print("Бот запущен")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()