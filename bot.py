import os
import requests

from urllib.parse import quote
from threading import Thread
from flask import Flask

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile
)

from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from deezer import (
    search_album,
    get_album_by_id,
    search_artist,
    get_artist_albums
)

from music_parser import (
    extract_title_from_page,
    extract_deezer_album_id
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

TARGET_THREAD_ID = None

# ---------------- FLASK ----------------

app_flask = Flask(__name__)


@app_flask.route("/")
def home():
    return "Bot is running"


def run_web():
    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app_flask.run(
        host="0.0.0.0",
        port=port
    )


Thread(
    target=run_web
).start()

# --------------------------------------


def format_release_date(date_string):

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

    parts = date_string.split("-")

    if len(parts) != 3:
        return date_string

    year, month, day = parts

    month_name = months.get(
        month,
        month
    )

    return (
        f"{month_name} "
        f"{int(day)}, "
        f"{year}"
    )


def format_duration(seconds):

    hours = seconds // 3600
    minutes = (
        seconds % 3600
    ) // 60

    secs = seconds % 60

    if hours > 0:
        return (
            f"{hours}:"
            f"{minutes:02}:"
            f"{secs:02}"
        )

    return (
        f"{minutes:02}:"
        f"{secs:02}"
    )


async def send_album(
    context,
    chat_id,
    album
):

    title = album.get(
        "title",
        "Unknown"
    )

    artists_list = []

    contributors = album.get(
        "contributors",
        []
    )

    if contributors:

        for artist in contributors:

            name = artist.get("name")

            if (
                name
                and name not in artists_list
            ):
                artists_list.append(name)

    else:

        main_artist = (
            album.get("artist", {})
            .get("name")
        )

        if main_artist:
            artists_list.append(
                main_artist
            )

    artists = ", ".join(
        artists_list
    )

    release_date = (
        format_release_date(
            album.get(
                "release_date",
                "Unknown"
            )
        )
    )

    tracks = album.get(
        "full_tracks",
        []
    )

    total_tracks = len(tracks)

    total_duration = sum(
        track.get("duration", 0)
        for track in tracks
    )

    duration_text = (
        format_duration(
            total_duration
        )
    )

    cover_url = (
        album.get("cover_xl")
        or album.get("cover_big")
        or album.get("cover")
    )

    track_lines = []

    for track in tracks:

        track_name = track.get(
            "title",
            "Unknown Track"
        )

        track_lines.append(
            track_name
        )

    tracklist = "\n".join(
        track_lines
    )

    caption = (
        f"🎵 {title}\n\n"
        f"👥 {artists}\n\n"
        f"📅 {release_date}\n"
        f"💿 {total_tracks} tracks\n"
        f"⏳ {duration_text}\n\n"
        f"---Tracklist---\n\n"
        f"{tracklist}"
    )

    search_query = quote(
        f"{title} {artists}"
    )

    spotify_url = (
        "https://open.spotify.com/search/"
        f"{search_query}"
    )

    apple_music_url = (
        "https://music.apple.com/us/search"
        f"?term={search_query}"
    )

    deezer_url = album.get(
        "link"
    )

    youtube_music_url = (
        "https://music.youtube.com/search"
        f"?q={search_query}"
    )

    soundcloud_url = (
        "https://soundcloud.com/search"
        f"?q={search_query}"
    )

    tidal_url = (
        "https://listen.tidal.com/search"
        f"?query={search_query}"
    )

    artist_name = (
        album.get("artist", {})
        .get("name", "")
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "Spotify",
                url=spotify_url
            ),

            InlineKeyboardButton(
                "Apple Music",
                url=apple_music_url
            ),

            InlineKeyboardButton(
                "Deezer",
                url=deezer_url
            )
        ],

        [
            InlineKeyboardButton(
                "YouTube Music",
                url=youtube_music_url
            ),

            InlineKeyboardButton(
                "SoundCloud",
                url=soundcloud_url
            ),

            InlineKeyboardButton(
                "Tidal",
                url=tidal_url
            )
        ],

        [
            InlineKeyboardButton(
                f"View More From {artist_name}",
                callback_data=(
                    f"artist:{artist_name}"
                )
            )
        ]
    ])

    if cover_url:

        image_response = requests.get(
            cover_url,
            timeout=15
        )

        image_data = (
            image_response.content
        )

        filename = (
            f"{title}.jpg"
        )

        with open(
            filename,
            "wb"
        ) as f:

            f.write(image_data)

        with open(
            filename,
            "rb"
        ) as photo:

            await context.bot.send_document(
                chat_id=chat_id,
                document=InputFile(
                    photo,
                    filename=filename
                ),
                caption=caption,
                reply_markup=keyboard
            )

        os.remove(filename)


async def handle_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data

    if data.startswith(
        "artist:"
    ):

        artist_name = (
            data.replace(
                "artist:",
                ""
            )
        )

        artist = search_artist(
            artist_name
        )

        if not artist:
            return

        albums = (
            get_artist_albums(
                artist["id"]
            )
        )

        buttons = []

        for album in albums[:20]:

            album_title = (
                album["title"]
            )

            album_id = (
                album["id"]
            )

            buttons.append([
                InlineKeyboardButton(
                    album_title,
                    callback_data=(
                        f"album:{album_id}"
                    )
                )
            ])

        keyboard = (
            InlineKeyboardMarkup(
                buttons
            )
        )

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                f"Albums by "
                f"{artist_name}:"
            ),
            reply_markup=keyboard
        )

    elif data.startswith(
        "album:"
    ):

        album_id = (
            data.replace(
                "album:",
                ""
            )
        )

        album = (
            get_album_by_id(
                album_id
            )
        )

        await send_album(
            context,
            query.message.chat_id,
            album
        )


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if TARGET_THREAD_ID is not None:

        if (
            update.message.message_thread_id
            != TARGET_THREAD_ID
        ):
            return

    text = update.message.text

    if not text:
        return

    album = None

    try:

        if (
            "open.spotify.com"
            in text
        ):

            title = (
                extract_title_from_page(
                    text
                )
            )

            if title:
                album = (
                    search_album(
                        title
                    )
                )

        elif (
            "music.apple.com"
            in text
        ):

            title = (
                extract_title_from_page(
                    text
                )
            )

            if title:
                album = (
                    search_album(
                        title
                    )
                )

        elif (
            "deezer.com"
            in text
        ):

            album_id = (
                extract_deezer_album_id(
                    text
                )
            )

            if album_id:
                album = (
                    get_album_by_id(
                        album_id
                    )
                )

        else:

            artist = search_artist(
                text
            )

            if artist:

                albums = (
                    get_artist_albums(
                        artist["id"]
                    )
                )

                buttons = []

                for album_item in albums[:20]:

                    buttons.append([
                        InlineKeyboardButton(
                            album_item[
                                "title"
                            ],
                            callback_data=(
                                f"album:{album_item['id']}"
                            )
                        )
                    ])

                keyboard = (
                    InlineKeyboardMarkup(
                        buttons
                    )
                )

                await context.bot.send_message(
                    chat_id=(
                        update.message.chat_id
                    ),
                    text=(
                        f"Albums by "
                        f"{artist['name']}:"
                    ),
                    reply_markup=keyboard
                )

                return

            album = search_album(
                text
            )

        if not album:

            await context.bot.send_message(
                chat_id=(
                    update.message.chat_id
                ),
                text="Album not found."
            )

            return

        await send_album(
            context,
            update.message.chat_id,
            album
        )

    except Exception as e:

        print(e)

        await context.bot.send_message(
            chat_id=(
                update.message.chat_id
            ),
            text=f"Error:\n{e}"
        )


def main():

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_message
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            handle_callback
        )
    )

    print("Bot started.")

    app.run_polling()


if __name__ == "__main__":
    main()