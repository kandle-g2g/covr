import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
TARGET_THREAD_ID = int(os.getenv("TARGET_THREAD_ID", "0"))

app_flask = Flask(__name__)


@app_flask.route("/")
def home():
    return "Bot is running!"


# =========================
# HELPERS
# =========================

def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def format_duration(ms):
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02}"


def search_album(query):
    url = f"https://api.deezer.com/search/album?q={query}"
    data = requests.get(url).json()

    if not data.get("data"):
        return None

    return data["data"][:10]


def get_album(album_id):
    url = f"https://api.deezer.com/album/{album_id}"
    return requests.get(url).json()


def build_album_caption(album):
    artist = album["artist"]["name"]
    title = album["title"]

    duration = format_duration(album["duration"] * 1000)
    tracks_count = album["nb_tracks"]

    caption = (
        f"🎵 <b>{title}</b>\n"
        f"👤 {artist}\n"
        f"⏳ {duration}\n"
        f"🎼 {tracks_count} tracks\n\n"
        f"---Tracklist---\n"
    )

    for i, track in enumerate(album["tracks"]["data"], start=1):
        duration = format_duration(track["duration"] * 1000)

        caption += (
            f"\n{i}. {track['title']} "
            f"({duration})"
        )

    return caption


def build_service_buttons(album):
    title = album["title"]
    artist = album["artist"]["name"]

    query = requests.utils.quote(f"{artist} {title}")

    spotify = f"https://open.spotify.com/search/{query}"
    apple = f"https://music.apple.com/us/search?term={query}"
    deezer = f"https://www.deezer.com/search/{query}"

    artist_query = requests.utils.quote(artist)
    artist_link = f"https://www.deezer.com/search/{artist_query}"

    keyboard = [
        [
            InlineKeyboardButton("Spotify", url=spotify),
            InlineKeyboardButton("Apple Music", url=apple),
            InlineKeyboardButton("Deezer", url=deezer),
        ],
        [
            InlineKeyboardButton(
                f"More albums by {artist}",
                callback_data=f"artist::{artist}"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================
# SEND ALBUM
# =========================

async def send_album(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    album_id: int,
):
    album = get_album(album_id)

    caption = build_album_caption(album)
    keyboard = build_service_buttons(album)

    image = album["cover_xl"]

    await update.effective_chat.send_photo(
        photo=image,
        caption=caption,
        parse_mode="HTML",
        reply_markup=keyboard,
        message_thread_id=update.message.message_thread_id
        if update.message
        else update.callback_query.message.message_thread_id
    )


# =========================
# MESSAGE HANDLER
# =========================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return

    # =========================
    # THREAD FILTER
    # =========================

    if update.effective_chat.type in ["group", "supergroup"]:
        thread_id = update.message.message_thread_id

        if TARGET_THREAD_ID and thread_id != TARGET_THREAD_ID:
            return

    query = clean(update.message.text)

    results = search_album(query)

    if not results:
        await update.message.reply_text(
            "Nothing found.",
            message_thread_id=update.message.message_thread_id
        )
        return

    # =========================
    # IF MANY ALBUMS
    # =========================

    if len(results) > 1:
        keyboard = []

        for album in results[:10]:
            artist = album["artist"]["name"]
            title = album["title"]

            keyboard.append([
                InlineKeyboardButton(
                    f"{artist} — {title}",
                    callback_data=f"album::{album['id']}"
                )
            ])

        await update.message.reply_text(
            "Choose album:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            message_thread_id=update.message.message_thread_id
        )

        return

    # =========================
    # SINGLE RESULT
    # =========================

    album_id = results[0]["id"]

    await send_album(update, context, album_id)


# =========================
# BUTTONS
# =========================

async def handle_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    data = query.data

    # =========================
    # OPEN ALBUM
    # =========================

    if data.startswith("album::"):
        album_id = int(data.split("::")[1])

        album = get_album(album_id)

        caption = build_album_caption(album)
        keyboard = build_service_buttons(album)

        await query.message.reply_photo(
            photo=album["cover_xl"],
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
            message_thread_id=query.message.message_thread_id
        )

    # =========================
    # ARTIST ALBUMS
    # =========================

    elif data.startswith("artist::"):
        artist_name = data.split("::")[1]

        albums = search_album(artist_name)

        if not albums:
            return

        keyboard = []

        for album in albums[:10]:
            keyboard.append([
                InlineKeyboardButton(
                    album["title"],
                    callback_data=f"album::{album['id']}"
                )
            ])

        await query.message.reply_text(
            f"Albums by {artist_name}:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            message_thread_id=query.message.message_thread_id
        )


# =========================
# MAIN
# =========================

def main():
    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    application.add_handler(
        CallbackQueryHandler(handle_buttons)
    )

    print("Bot started.")

    application.run_polling()


if __name__ == "__main__":
    from threading import Thread

    port = int(os.environ.get("PORT", 10000))

    Thread(
        target=lambda: app_flask.run(
            host="0.0.0.0",
            port=port
        )
    ).start()

    main()