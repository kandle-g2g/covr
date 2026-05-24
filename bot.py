import os
import re
import requests
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


def format_duration(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    sec = seconds % 60

    # если меньше часа
    if hours == 0:
        return f"{minutes}:{sec:02}"

    return f"{hours}:{minutes:02}:{sec:02}"


def track_duration(seconds):
    minutes = seconds // 60
    sec = seconds % 60

    return f"{minutes}:{sec:02}"


def search_album(query):
    url = f"https://api.deezer.com/search/album?q={query}"
    response = requests.get(url).json()

    if not response.get("data"):
        return []

    return response["data"]


def get_album(album_id):
    url = f"https://api.deezer.com/album/{album_id}"
    return requests.get(url).json()


def build_album_caption(album):
    title = album["title"]

    # ВСЕ артисты
    contributors = album.get("contributors", [])

    if contributors:
        artists = ", ".join(
            dict.fromkeys([a["name"] for a in contributors])
        )
    else:
        artists = album["artist"]["name"]

    release_date = album.get("release_date", "")
    duration = format_duration(album["duration"])
    tracks_count = album["nb_tracks"]

    # красивая дата
    formatted_date = release_date

    try:
        from datetime import datetime

        dt = datetime.strptime(release_date, "%Y-%m-%d")
        formatted_date = dt.strftime("%B %d, %Y")

    except:
        pass

    caption = (
        f"🎵 <b>{title}</b>\n\n"
        f"👥 {artists}\n\n"
        f"📅 {formatted_date}\n"
        f"💿 {tracks_count} tracks\n"
        f"⏳ {duration}\n\n"
        f"---Tracklist---\n"
    )

    for track in album["tracks"]["data"]:
        caption += f"\n{track['title']}"

    return caption


def build_service_buttons(album):
    title = album["title"]
    artist = album["artist"]["name"]

    query = requests.utils.quote(f"{artist} {title}")

    spotify = f"https://open.spotify.com/search/{query}"
    apple = f"https://music.apple.com/us/search?term={query}"
    deezer = f"https://www.deezer.com/search/{query}"
    tidal = f"https://listen.tidal.com/search?q={query}"
    youtube = f"https://music.youtube.com/search?q={query}"
    soundcloud = f"https://soundcloud.com/search?q={query}"

    keyboard = [
        [
            InlineKeyboardButton("Spotify", url=spotify),
            InlineKeyboardButton("Apple", url=apple),
            InlineKeyboardButton("Deezer", url=deezer),
        ],
        [
            InlineKeyboardButton("TIDAL", url=tidal),
            InlineKeyboardButton("YouTube", url=youtube),
            InlineKeyboardButton("SoundCloud", url=soundcloud),
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

    thread_id = None

    if update.message:
        thread_id = update.message.message_thread_id

    elif update.callback_query:
        thread_id = update.callback_query.message.message_thread_id

    await update.effective_chat.send_document(
        document=image,
        caption=caption,
        parse_mode="HTML",
        reply_markup=keyboard,

        # название файла = название альбома
        filename=f"{album['title']}.jpg",

        message_thread_id=thread_id
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

    keyboard = []
    added = set()

    for album in results[:25]:
        artist = album["artist"]["name"]
        title = album["title"]

        key = f"{artist}-{title}"

        if key in added:
            continue

        added.add(key)

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


# =========================
# BUTTON HANDLER
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

        await send_album(update, context, album_id)

    # =========================
    # ARTIST ALBUMS
    # =========================

    elif data.startswith("artist::"):
        artist_name = data.split("::")[1]

        albums = search_album(artist_name)

        if not albums:
            return

        keyboard = []
        added = set()

        for album in albums[:25]:
            title = album["title"]

            if title in added:
                continue

            added.add(title)

            keyboard.append([
                InlineKeyboardButton(
                    title,
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