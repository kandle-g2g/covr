from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import requests
import tempfile
import os
import re
import json

from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread


BOT_TOKEN = os.getenv("BOT_TOKEN")
TARGET_THREAD_ID = os.getenv("TARGET_THREAD_ID")

if TARGET_THREAD_ID:
    TARGET_THREAD_ID = int(TARGET_THREAD_ID)


# =========================================
# KEEP RENDER ALIVE
# =========================================

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "OK"


def run_web():
    flask_app.run(
        host="0.0.0.0",
        port=10000
    )


# =========================================
# HELPERS
# =========================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def clean_text(text):

    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def is_music_link(text):

    services = [
        "spotify.com",
        "music.apple.com",
        "deezer.com",
    ]

    return any(
        service in text
        for service in services
    )


# =========================================
# SPOTIFY PARSER
# =========================================

def extract_spotify_metadata(url: str):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=20
    )

    if response.status_code != 200:
        raise Exception(
            "Spotify link open failed"
        )

    html = response.text

    match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        html,
        re.DOTALL
    )

    if not match:
        raise Exception(
            "Spotify metadata not found"
        )

    data = json.loads(
        match.group(1)
    )

    album_name = clean_text(
        data.get("name")
    )

    artists = []

    by_artist = data.get(
        "byArtist"
    )

    if isinstance(by_artist, list):

        for artist in by_artist:

            name = clean_text(
                artist.get("name")
            )

            if name:
                artists.append(name)

    elif isinstance(by_artist, dict):

        name = clean_text(
            by_artist.get("name")
        )

        if name:
            artists.append(name)

    cover = data.get("image")

    return {
        "album_name": album_name,
        "artists": ", ".join(artists),
        "cover": cover
    }


# =========================================
# APPLE MUSIC PARSER
# =========================================

def extract_apple_music_metadata(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=20
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title = soup.title.text.strip()

    # Example:
    # "Graduation by Kanye West on Apple Music"

    album_name = title
    artists = "Unknown Artist"

    if " by " in title:

        parts = title.split(
            " by ",
            1
        )

        album_name = parts[0].strip()

        artists = (
            parts[1]
            .replace("on Apple Music", "")
            .strip()
        )

    cover = None

    og_image = soup.find(
        "meta",
        property="og:image"
    )

    if og_image:
        cover = og_image.get("content")

    return {
        "album_name": album_name,
        "artists": artists,
        "cover": cover
    }


# =========================================
# DEEZER PARSER
# =========================================

def extract_deezer_metadata(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=20
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title = soup.title.text.strip()

    album_name = (
        title
        .replace("| Deezer", "")
        .strip()
    )

    artist = "Unknown Artist"

    artist_meta = soup.find(
        "meta",
        property="music:musician_description"
    )

    if artist_meta:
        artist = artist_meta.get(
            "content"
        )

    cover = None

    og_image = soup.find(
        "meta",
        property="og:image"
    )

    if og_image:
        cover = og_image.get("content")

    return {
        "album_name": album_name,
        "artists": artist,
        "cover": cover
    }


# =========================================
# UNIVERSAL URL PARSER
# =========================================

def parse_music_url(url):

    print("URL:", url)

    if "spotify.com" in url:

        parsed = extract_spotify_metadata(
            url
        )

    elif "music.apple.com" in url:

        parsed = extract_apple_music_metadata(
            url
        )

    elif "deezer.com" in url:

        parsed = extract_deezer_metadata(
            url
        )

    else:
        raise Exception(
            "Unsupported link"
        )

    print("PARSED:", parsed)

    return parsed


# =========================================
# DEEZER SEARCH
# =========================================

def get_all_tracks(tracklist_url):

    all_tracks = []

    url = tracklist_url

    while url:

        response = requests.get(
            url,
            timeout=15
        )

        data = response.json()

        all_tracks.extend(
            data.get("data", [])
        )

        url = data.get("next")

    return all_tracks


def get_album_by_id(album_id):

    response = requests.get(
        f"https://api.deezer.com/album/{album_id}",
        timeout=15
    )

    album = response.json()

    album["full_tracks"] = (
        get_all_tracks(
            album["tracklist"]
        )
    )

    total_duration = sum(
        track.get("duration", 0)
        for track in album["full_tracks"]
    )

    album["duration"] = total_duration

    album["nb_tracks"] = len(
        album["full_tracks"]
    )

    return album


def search_album(query):

    response = requests.get(
        "https://api.deezer.com/search/album",
        params={
            "q": query
        },
        timeout=15
    )

    data = response.json()

    albums = data.get("data")

    if not albums:
        return None

    album_id = albums[0]["id"]

    return get_album_by_id(album_id)


# =========================================
# FORMATTERS
# =========================================

def format_duration(seconds):

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    sec = seconds % 60

    if hours == 0:
        return f"{minutes}:{sec:02}"

    return f"{hours}:{minutes:02}:{sec:02}"


def build_caption(album):

    contributors = album.get(
        "contributors",
        []
    )

    if contributors:

        artists = ", ".join(
            dict.fromkeys(
                [
                    a["name"]
                    for a in contributors
                ]
            )
        )

    else:

        artists = album["artist"]["name"]

    title = album["title"]

    release_date = album.get(
        "release_date",
        ""
    )

    duration = format_duration(
        album["duration"]
    )

    tracks_count = album["nb_tracks"]

    caption = (
        f"🎵 <b>{title}</b>\n\n"
        f"👥 {artists}\n\n"
        f"📅 {release_date}\n"
        f"💿 {tracks_count} tracks\n"
        f"⏳ {duration}\n\n"
        f"---Tracklist---\n"
    )

    for track in album["full_tracks"]:

        caption += (
            f"\n{track['title']}"
        )

    return caption


# =========================================
# BUTTONS
# =========================================

def build_buttons(album):

    title = album["title"]
    artist = album["artist"]["name"]

    query = requests.utils.quote(
        f"{artist} {title}"
    )

    buttons = [

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
                "TIDAL",
                url=f"https://listen.tidal.com/search?q={query}"
            ),

            InlineKeyboardButton(
                "YouTube",
                url=f"https://music.youtube.com/search?q={query}"
            ),
        ],

        [
            InlineKeyboardButton(
                "SoundCloud",
                url=f"https://soundcloud.com/search?q={query}"
            ),

            InlineKeyboardButton(
                "Deezer",
                url=f"https://www.deezer.com/search/{query}"
            ),
        ]
    ]

    return InlineKeyboardMarkup(
        buttons
    )


# =========================================
# SEND ALBUM
# =========================================

async def send_album(
    update,
    album
):

    caption = build_caption(album)

    keyboard = build_buttons(
        album
    )

    image_url = album["cover_xl"]

    response = requests.get(
        image_url
    )

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".jpg"
    ) as temp_file:

        temp_file.write(
            response.content
        )

        temp_path = temp_file.name

    album_name = re.sub(
        r'[\\/*?:"<>|]',
        "",
        album["title"]
    )

    thread_id = None

    if update.message:
        thread_id = (
            update.message
            .message_thread_id
        )

    with open(temp_path, "rb") as cover:

        await update.effective_chat.send_document(
            document=cover,
            filename=f"{album_name}.jpg",
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
            message_thread_id=thread_id
        )


# =========================================
# MESSAGE HANDLER
# =========================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if (
        TARGET_THREAD_ID
        and update.message.chat.type
        in ["supergroup", "group"]
    ):

        current_thread = (
            update.message.message_thread_id
        )

        if current_thread != TARGET_THREAD_ID:
            return

    text = (
        update.message.text.strip()
    )

    try:

        # =====================
        # LINK SEARCH
        # =====================

        if is_music_link(text):

            parsed = parse_music_url(
                text
            )

            query = (
                f"{parsed['album_name']} "
                f"{parsed['artists']}"
            )

            print(
                "SEARCH QUERY:",
                query
            )

            album = search_album(
                query
            )

        # =====================
        # TEXT SEARCH
        # =====================

        else:

            album = search_album(
                text
            )

        if not album:

            await update.message.reply_text(
                "Album not found."
            )

            return

        await send_album(
            update,
            album
        )

    except Exception as e:

        print(e)

        await update.message.reply_text(
            f"Error:\n{str(e)}"
        )


# =========================================
# MAIN
# =========================================

def main():

    Thread(
        target=run_web
    ).start()

    app = (
        ApplicationBuilder()
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

    print("Bot started.")

    app.run_polling()


if __name__ == "__main__":
    main()