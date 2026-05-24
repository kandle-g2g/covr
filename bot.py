import os
import re
import json
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

            if not script.string:
                continue

            data = json.loads(
                script.string
            )

            if data.get("@type") != "MusicAlbum":
                continue

            album_name = data.get("name")

            artists = []

            by_artist = data.get(
                "byArtist"
            )

            if isinstance(by_artist, list):

                for artist in by_artist:

                    if artist.get("name"):
                        artists.append(
                            artist["name"]
                        )

            elif isinstance(by_artist, dict):

                if by_artist.get("name"):
                    artists.append(
                        by_artist["name"]
                    )

            return {
                "album_name": album_name,
                "artists": ", ".join(artists),
                "cover": data.get("image")
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

    if len(parts) < 2:
        raise Exception(
            "Deezer metadata not found"
        )

    album_name = (
        parts[0]
        .replace("album", "")
        .strip()
    )

    artists = (
        parts[1]
        .split("|")[0]
        .strip()
    )

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

    if len(parts) < 2:
        raise Exception(
            "Apple metadata not found"
        )

    album_name = (
        parts[0]
        .replace("on Apple Music", "")
        .strip()
    )

    artists = (
        parts[1]
        .split("on")[0]
        .strip()
    )

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


def parse_music_url(url: str):

    if "spotify.com" in url:
        return extract_spotify_metadata(url)

    if "deezer.com" in url:
        return extract_deezer_metadata(url)

    if "music.apple.com" in url:
        return extract_apple_metadata(url)

    raise Exception(
        "Unsupported link"
    )


def search_album(query: str):

    response = requests.get(
        "https://api.deezer.com/search/album",
        params={
            "q": query
        },
        timeout=15
    )

    data = response.json()

    albums = data.get("data", [])

    if not albums:
        return None

    return albums[0]


def search_artist(query: str):

    response = requests.get(
        "https://api.deezer.com/search/artist",
        params={
            "q": query
        },
        timeout=15
    )

    data = response.json()

    artists = data.get("data", [])

    if not artists:
        return None

    return artists[0]


def get_artist_albums(artist_id):

    response = requests.get(
        f"https://api.deezer.com/artist/{artist_id}/albums",
        timeout=15
    )

    data = response.json()

    albums = []
    seen = set()

    for album in data.get("data", []):

        title = album.get("title")

        if not title:
            continue

        if title.lower() in seen:
            continue

        seen.add(
            title.lower()
        )

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

    tracks_data = data.get(
        "tracks",
        {}
    )

    while True:

        current_tracks = tracks_data.get(
            "data",
            []
        )

        for track in current_tracks:

            title = track.get(
                "title",
                "Unknown Track"
            )

            tracks.append(title)

            total_duration += int(
                track.get(
                    "duration",
                    0
                )
            )

        next_url = tracks_data.get(
            "next"
        )

        if not next_url:
            break

        next_response = requests.get(
            next_url,
            timeout=15
        )

        tracks_data = next_response.json()

    contributors = data.get(
        "contributors",
        []
    )

    artists = []

    for contributor in contributors:

        name = contributor.get(
            "name"
        )

        if (
            name
            and name not in artists
        ):
            artists.append(name)

    artist_data = data.get(
        "artist",
        {}
    )

    return {

        "title": data.get(
            "title",
            "Unknown Album"
        ),

        "artist": ", ".join(artists)
        if artists
        else artist_data.get(
            "name",
            "Unknown Artist"
        ),

        "release_date": data.get(
            "release_date",
            "Unknown Date"
        ),

        "tracks_count": len(tracks),

        "duration": format_duration(
            total_duration
        ),

        "cover": data.get(
            "cover_xl"
        ),

        "tracks": tracks,

        "deezer_url": data.get(
            "link"
        ),

        "artist_url": artist_data.get(
            "link",
            f"https://www.deezer.com/artist/{artist_data.get('id', '')}"
        ),

        "artist_name": artist_data.get(
            "name",
            artists[0] if artists else "Unknown Artist"
        ),
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

    query = requests.utils.quote(
        f"{artist} {title}"
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
            )
        ],

        [
            InlineKeyboardButton(
                "Deezer",
                url=f"https://www.deezer.com/search/{query}"
            ),

            InlineKeyboardButton(
                "TIDAL",
                url=f"https://listen.tidal.com/search?q={query}"
            )
        ],

        [
            InlineKeyboardButton(
                "YouTube",
                url=f"https://music.youtube.com/search?q={query}"
            ),

            InlineKeyboardButton(
                "SoundCloud",
                url=f"https://soundcloud.com/search?q={query}"
            )
        ],

        [
            InlineKeyboardButton(
                "Other releases",
                callback_data=f"artist::{artist}"
            )
        ]
    ]

    return InlineKeyboardMarkup(
        keyboard
    )

async def send_album(
    update,
    context,
    album_id
):

    album_info = get_album(
        album_id
    )

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

    image_bytes.name = (
        f"{safe_name}.jpg"
    )

    target_message = None

    if getattr(update, "callback_query", None):

        target_message = (
            update.callback_query.message
        )

    elif getattr(update, "message", None):

        target_message = (
            update.message
        )

    if not target_message:
        return

    kwargs = {}

    if (
        TARGET_THREAD_ID
        and target_message.chat.type
        in ["group", "supergroup"]
    ):

        kwargs["message_thread_id"] = int(
            TARGET_THREAD_ID
        )

    await target_message.reply_document(
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
        in ["group", "supergroup"]
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

               # =========================
        # MUSIC LINKS
        # =========================

        if (
            "spotify.com" in text
            or "deezer.com" in text
            or "music.apple.com" in text
        ):

            parsed = parse_music_url(
                text
            )

            album_name = clean_query(
                parsed.get(
                    "album_name",
                    ""
                )
            )

            artists = clean_query(
                parsed.get(
                    "artists",
                    ""
                )
            )

            search_queries = [

                f"{album_name} {artists}",

                album_name,

                f"{artists} {album_name}",
            ]

            album = None

            for q in search_queries:

                print(
                    "TRYING:",
                    q
                )

                album = search_album(q)

                if album:
                    break

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
        
        
               # =========================
        # ARTIST DETECTION
        # =========================

        artist = search_artist(text)

        if artist:

            artist_name = artist["name"].lower().strip()
            user_query = text.lower().strip()

            # exact artist search
            if (
                artist_name == user_query
                or user_query in artist_name
                or artist_name in user_query
            ):

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

        # =========================
        # ALBUM SEARCH
        # =========================

        album = search_album(text)

        if album:

            await send_album(
                update,
                context,
                album["id"]
            )

            return

        await update.message.reply_text(
            "Album not found"
        )

    except Exception as e:

        print(e)

        await update.message.reply_text(
            f"Error:\n{str(e)}"
        )

def main():

    asyncio.set_event_loop(
        asyncio.new_event_loop()
    )

    web_thread = Thread(
        target=run_web
    )

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