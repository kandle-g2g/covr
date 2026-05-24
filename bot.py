import os
import re
import json
import html
import asyncio
import requests

from io import BytesIO
from threading import Thread
from flask import Flask

from bs4 import BeautifulSoup

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)

from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_THREAD_ID = os.getenv("TARGET_THREAD_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "OK"


def run_web():
    flask_app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )


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


def extract_spotify_metadata(url: str):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=15
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:

        try:
            data = json.loads(script.string)

            if data.get("@type") == "MusicAlbum":

                album_name = data.get("name")

                artists = []

                by_artist = data.get("byArtist")

                if isinstance(by_artist, list):

                    for artist in by_artist:
                        artists.append(
                            artist.get("name")
                        )

                elif isinstance(by_artist, dict):

                    artists.append(
                        by_artist.get("name")
                    )

                cover = data.get("image")

                return {
                    "album_name": album_name,
                    "artists": ", ".join(artists),
                    "cover": cover
                }

        except:
            pass

    raise Exception(
        "Spotify metadata not found"
    )


def extract_deezer_metadata(url: str):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=15
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title = soup.title.string.strip()

    parts = title.split("by")

    if len(parts) >= 2:

        album_name = parts[0].replace(
            "album",
            ""
        ).strip()

        artists = parts[1].split("|")[0].strip()

        cover = None

        meta = soup.find(
            "meta",
            property="og:image"
        )

        if meta:
            cover = meta.get("content")

        return {
            "album_name": album_name,
            "artists": artists,
            "cover": cover
        }

    raise Exception(
        "Deezer metadata not found"
    )


def extract_apple_metadata(url: str):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=15
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title = soup.title.string.strip()

    parts = title.split("by")

    if len(parts) >= 2:

        album_name = parts[0].replace(
            "on Apple Music",
            ""
        ).strip()

        artists = parts[1].split("on")[0].strip()

        cover = None

        meta = soup.find(
            "meta",
            property="og:image"
        )

        if meta:
            cover = meta.get("content")

        return {
            "album_name": album_name,
            "artists": artists,
            "cover": cover
        }

    raise Exception(
        "Apple Music metadata not found"
    )


def parse_music_url(url: str):

    if "spotify.com" in url:
        return extract_spotify_metadata(url)

    if "deezer.com" in url:
        return extract_deezer_metadata(url)

    if "music.apple.com" in url:
        return extract_apple_metadata(url)

    raise Exception("Unsupported link")


def search_album(query: str):

    response = requests.get(
        "https://api.deezer.com/search/album",
        params={
            "q": query
        },
        timeout=15
    )

    data = response.json()

    if not data.get("data"):
        return None

    return data["data"][0]


def search_artist(artist_name: str):

    response = requests.get(
        "https://api.deezer.com/search/artist",
        params={
            "q": artist_name
        },
        timeout=15
    )

    data = response.json()

    if not data.get("data"):
        return None

    return data["data"][0]


def get_artist_albums(artist_id):

    response = requests.get(
        f"https://api.deezer.com/artist/{artist_id}/albums",
        timeout=15
    )

    data = response.json()

    albums = []

    seen = set()

    for album in data.get("data", []):

        title = album["title"]

        if title.lower() in seen:
            continue

        seen.add(title.lower())

        albums.append({
            "id": album["id"],
            "title": title
        })

    return albums[:20]


def get_album(album_id):

    response = requests.get(
        f"https://api.deezer.com/album/{album_id}",
        timeout=15
    )

    data = response.json()

    tracks = []

    total_duration = 0

    next_url = data["tracks"].get("next")
    current_tracks = data["tracks"]["data"]

    while True:

        for track in current_tracks:

            tracks.append(track["title"])
            total_duration += track["duration"]

        if not next_url:
            break

        next_response = requests.get(
            next_url,
            timeout=15
        )

        next_data = next_response.json()

        current_tracks = next_data["data"]
        next_url = next_data.get("next")

    artists = []

    contributors = data.get(
        "contributors",
        []
    )

    for artist in contributors:

        name = artist.get("name")

        if name and name not in artists:
            artists.append(name)

    return {
        "title": data["title"],
        "artist": ", ".join(artists),
        "release_date": data["release_date"],
        "tracks_count": len(tracks),
        "duration": format_duration(total_duration),
        "cover": data["cover_xl"],
        "tracks": tracks,
        "deezer_url": data["link"],
        "artist_url": data["artist"]["link"],
        "artist_name": data["artist"]["name"]
    }


def build_album_caption(album_info):

    tracklist = "\n".join(
        album_info["tracks"]
    )

    return (
        f"🎵 {album_info['title']}\n\n"
        f"👥 {album_info['artist']}\n\n"
        f"📅 {album_info['release_date']}\n"
        f"💿 {album_info['tracks_count']} tracks\n"
        f"⏳ {album_info['duration']}\n\n"
        f"---Tracklist---\n\n"
        f"{tracklist}"
    )


def build_album_buttons(album_info):

    title = album_info["title"]
    artist = album_info["artist_name"]

    spotify_query = requests.utils.quote(
        f"{artist} {title}"
    )

    tidal_query = requests.utils.quote(
        f"{artist} {title}"
    )

    youtube_query = requests.utils.quote(
        f"{artist} {title}"
    )

    soundcloud_query = requests.utils.quote(
        f"{artist} {title}"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "Spotify",
                url=f"https://open.spotify.com/search/{spotify_query}"
            ),

            InlineKeyboardButton(
                "Apple Music",
                url=f"https://music.apple.com/us/search?term={spotify_query}"
            )
        ],

        [
            InlineKeyboardButton(
                "TIDAL",
                url=f"https://listen.tidal.com/search?q={tidal_query}"
            ),

            InlineKeyboardButton(
                "YouTube",
                url=f"https://www.youtube.com/results?search_query={youtube_query}"
            )
        ],

        [
            InlineKeyboardButton(
                "SoundCloud",
                url=f"https://soundcloud.com/search?q={soundcloud_query}"
            )
        ],

        [
            InlineKeyboardButton(
                "Other releases",
                callback_data=f"artist::{artist}"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


async def send_album(
    update,
    context,
    album_id
):

    album_info = get_album(album_id)

    caption = build_album_caption(
        album_info
    )

    buttons = build_album_buttons(
        album_info
    )

    image_response = requests.get(
        album_info["cover"],
        timeout=15
    )

    image_bytes = BytesIO(
        image_response.content
    )

    safe_name = re.sub(
        r'[\\/*?:"<>|]',
        "",
        album_info["title"]
    )

    image_bytes.name = f"{safe_name}.jpg"

    if hasattr(update, "callback_query"):

        await update.callback_query.message.reply_document(
            document=InputFile(image_bytes),
            caption=caption,
            reply_markup=buttons
        )

    else:

        kwargs = {}

        if (
            TARGET_THREAD_ID
            and update.message.chat.type
            in ["supergroup", "group"]
        ):
            kwargs["message_thread_id"] = int(
                TARGET_THREAD_ID
            )

        await update.message.reply_document(
            document=InputFile(image_bytes),
            caption=caption,
            reply_markup=buttons,
            **kwargs
        )


async def handle_artist_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    artist_name = query.data.replace(
        "artist::",
        ""
    )

    artist = search_artist(
        artist_name
    )

    if not artist:

        await query.message.reply_text(
            "Artist not found"
        )

        return

    albums = get_artist_albums(
        artist["id"]
    )

    keyboard = []

    for album in albums:

        keyboard.append([
            InlineKeyboardButton(
                album["title"],
                callback_data=f"album::{album['id']}"
            )
        ])

    await query.message.reply_text(
        f"{artist_name} albums:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


async def handle_album_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    album_id = query.data.replace(
        "album::",
        ""
    )

    await send_album(
        update,
        context,
        album_id
    )


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if (
        TARGET_THREAD_ID
        and update.message.chat.type
        in ["supergroup", "group"]
    ):

        thread_id = getattr(
            update.message,
            "message_thread_id",
            None
        )

        if str(thread_id) != str(
            TARGET_THREAD_ID
        ):
            return

    text = update.message.text.strip()

    try:

        if "spotify.com" in text \
        or "deezer.com" in text \
        or "music.apple.com" in text:

            parsed = parse_music_url(text)

            search_query = (
                f"{parsed['album_name']} "
                f"{parsed['artists']}"
            )

            album = search_album(
                clean_query(search_query)
            )

            if not album:

                await update.message.reply_text(
                    "Album not found"
                )

                return

            await send_album(
                update,
                context,
                album["id"]
            )

            return

        artist = search_artist(text)

        if artist:

            albums = get_artist_albums(
                artist["id"]
            )

            keyboard = []

            for album in albums:

                keyboard.append([
                    InlineKeyboardButton(
                        album["title"],
                        callback_data=f"album::{album['id']}"
                    )
                ])

            await update.message.reply_text(
                f"{artist['name']} albums:",
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                )
            )

            return

        album = search_album(text)

        if not album:

            await update.message.reply_text(
                "Album not found"
            )

            return

        await send_album(
            update,
            context,
            album["id"]
        )

    except Exception as e:

        await update.message.reply_text(
            f"Error:\n{str(e)}"
        )


def main():

    asyncio.set_event_loop(
        asyncio.new_event_loop()
    )

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
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()