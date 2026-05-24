import os
import tempfile
import requests

from flask import Flask
from threading import Thread

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile
)

from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from music_parser import parse_music_url
from deezer import (
    search_album,
    get_album_tracks,
    search_artist_albums
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_THREAD_ID = os.getenv("TARGET_THREAD_ID")

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "OK"


def run_web():
    flask_app.run(host="0.0.0.0", port=10000)


def build_album_message(album_info):

    tracks_text = "\n".join(album_info["tracks"])

    return (
        f"🎵 {album_info['title']}\n\n"
        f"👥 {album_info['artist']}\n\n"
        f"📅 {album_info['release_date']}\n"
        f"💿 {album_info['track_count']} tracks\n"
        f"⏳ {album_info['duration']}\n\n"
        f"---Tracklist---\n\n"
        f"{tracks_text}"
    )


def build_service_buttons(album_info):

    query = requests.utils.quote(
        f"{album_info['artist']} {album_info['title']}"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "Spotify",
                url=f"https://open.spotify.com/search/{query}"
            ),
            InlineKeyboardButton(
                "Apple Music",
                url=f"https://music.apple.com/us/search?term={query}"
            ),
        ],
        [
            InlineKeyboardButton(
                "YouTube",
                url=f"https://www.youtube.com/results?search_query={query}"
            ),
            InlineKeyboardButton(
                "SoundCloud",
                url=f"https://soundcloud.com/search?q={query}"
            ),
        ],
        [
            InlineKeyboardButton(
                "TIDAL",
                url=f"https://listen.tidal.com/search?q={query}"
            ),
        ],
        [
            InlineKeyboardButton(
                "More from artist",
                callback_data=f"artist::{album_info['artist'].split(',')[0]}"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


async def send_album(update, album_info):

    message = build_album_message(album_info)

    keyboard = build_service_buttons(album_info)

    cover_url = album_info["cover"]

    if cover_url:

        image_data = requests.get(cover_url).content

        with tempfile.NamedTemporaryFile(
            suffix=".jpg",
            delete=False
        ) as temp_file:

            temp_file.write(image_data)

            safe_name = "".join(
                c for c in album_info["title"]
                if c.isalnum() or c in " -_"
            ).strip()

            filename = f"{safe_name}.jpg"

            with open(temp_file.name, "rb") as img:

                await update.message.reply_document(
                    document=InputFile(img, filename=filename),
                    caption=message,
                    reply_markup=keyboard
                )

    else:

        await update.message.reply_text(
            message,
            reply_markup=keyboard
        )


async def handle_artist_buttons(update, context):

    query = update.callback_query

    await query.answer()

    artist = query.data.split("::")[1]

    albums = search_artist_albums(artist)

    if not albums:
        await query.message.reply_text(
            "No albums found"
        )
        return

    keyboard = []

    for album in albums:

        keyboard.append([
            InlineKeyboardButton(
                album["title"],
                callback_data=f"album::{album['id']}"
            )
        ])

    await query.message.reply_text(
        f"Albums by {artist}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_album_buttons(update, context):

    query = update.callback_query

    await query.answer()

    album_id = query.data.split("::")[1]

    album_info = get_album_tracks(album_id)

    message = build_album_message(album_info)

    keyboard = build_service_buttons(album_info)

    cover_url = album_info["cover"]

    if cover_url:

        image_data = requests.get(cover_url).content

        with tempfile.NamedTemporaryFile(
            suffix=".jpg",
            delete=False
        ) as temp_file:

            temp_file.write(image_data)

            safe_name = "".join(
                c for c in album_info["title"]
                if c.isalnum() or c in " -_"
            ).strip()

            filename = f"{safe_name}.jpg"

            with open(temp_file.name, "rb") as img:

                await query.message.reply_document(
                    document=InputFile(img, filename=filename),
                    caption=message,
                    reply_markup=keyboard
                )


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if TARGET_THREAD_ID:

        thread_id = update.message.message_thread_id

        if str(thread_id) != str(TARGET_THREAD_ID):
            return

    text = update.message.text.strip()

    try:

        # =========================
        # MUSIC LINK
        # =========================

        if (
            "spotify.com/album/" in text
            or "deezer.com/album/" in text
            or "music.apple.com" in text
        ):

            parsed = parse_music_url(text)

            album = search_album(
                parsed["album_name"],
                parsed["artists"]
            )

            album_info = get_album_tracks(album["id"])

            await send_album(update, album_info)

            return

        # =========================
        # ARTIST SEARCH
        # =========================

        albums = search_artist_albums(text)

        if albums:

            keyboard = []

            for album in albums:

                keyboard.append([
                    InlineKeyboardButton(
                        album["title"],
                        callback_data=f"album::{album['id']}"
                    )
                ])

            await update.message.reply_text(
                f"Albums by {text}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            return

        # =========================
        # ALBUM SEARCH
        # =========================

        album = search_album(text)

        album_info = get_album_tracks(album["id"])

        await send_album(update, album_info)

    except Exception as e:

        await update.message.reply_text(
            f"Error:\n{str(e)}"
        )


def main():

    web_thread = Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    app = ApplicationBuilder().token(
        BOT_TOKEN
    ).build()

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            handle_artist_buttons,
            pattern=r"^artist::"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            handle_album_buttons,
            pattern=r"^album::"
        )
    )

    print("Bot started.")

    app.run_polling(
        drop_pending_updates=True,
        close_loop=False
    )

if __name__ == "__main__":
    main()