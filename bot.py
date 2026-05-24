import os
import re
import requests

from bs4 import BeautifulSoup
from urllib.parse import quote
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile
)
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters
)

# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID подтемы (если не нужен — оставь None)
TARGET_THREAD_ID = None

# =========================
# PARSERS
# =========================

def extract_title_from_page(url):

    headers = {
        "User-Agent": (
            "Mozilla/5.0"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=15
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title = soup.find("title")

    if not title:
        return None

    text = title.text.strip()

    # Spotify
    text = text.replace(
        " - Album by ",
        "|"
    )

    # Apple Music
    text = text.replace(
        " - Apple Music",
        ""
    )

    text = text.split("|")[0]

    return text.strip()


def extract_deezer_album_id(url):

    match = re.search(
        r"album/(\d+)",
        url
    )

    if not match:
        return None

    return match.group(1)

# =========================
# DEEZER API
# =========================

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

# =========================
# HELPERS
# =========================

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

    month_name = months.get(month, month)

    return f"{month_name} {int(day)}, {year}"


def format_duration(seconds):

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02}:{secs:02}"

    return f"{minutes:02}:{secs:02}"

# =========================
# MAIN HANDLER
# =========================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    # Фильтр по подтеме
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

        # =========================
        # SPOTIFY
        # =========================

        if "open.spotify.com" in text:

            title = extract_title_from_page(
                text
            )

            if title:
                album = search_album(title)

        # =========================
        # APPLE MUSIC
        # =========================

        elif "music.apple.com" in text:

            title = extract_title_from_page(
                text
            )

            if title:
                album = search_album(title)

        # =========================
        # DEEZER
        # =========================

        elif "deezer.com" in text:

            album_id = extract_deezer_album_id(
                text
            )

            if album_id:
                album = get_album_by_id(
                    album_id
                )

        # =========================
        # ПРОСТО ПОИСК
        # =========================

        else:

            album = search_album(text)

        # =========================
        # НЕ НАЙДЕНО
        # =========================

        if not album:

            await update.message.reply_text(
                "Album not found."
            )

            return

        # =========================
        # DATA
        # =========================

        title = album.get("title", "Unknown")

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

        artists = ", ".join(artists_list)

        release_date = format_release_date(
            album.get(
                "release_date",
                "Unknown"
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

        duration_text = format_duration(
            total_duration
        )

        cover_url = (
            album.get("cover_xl")
            or album.get("cover_big")
            or album.get("cover")
        )

        # =========================
        # TRACKLIST
        # =========================

        track_lines = []

        for track in tracks:

            track_name = track.get(
                "title",
                "Unknown Track"
            )

            track_lines.append(
                track_name
            )

        tracklist = "\n".join(track_lines)

        # =========================
        # TEXT
        # =========================

        caption = (
            f"🎵 {title}\n\n"
            f"👥 {artists}\n\n"
            f"📅 {release_date}\n"
            f"💿 {total_tracks} tracks\n"
            f"⏱ {duration_text}\n\n"
            f"{tracklist}"
        )

        # =========================
        # BUTTONS
        # =========================

        spotify_url = (
            f"https://open.spotify.com/search/"
            f"{quote(title + ' ' + artists)}"
        )

        apple_music_url = (
            "https://music.apple.com/us/search"
            f"?term={quote(title + ' ' + artists)}"
        )

        deezer_url = album.get("link")

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "Spotify",
                    url=spotify_url
                ),

                InlineKeyboardButton(
                    "Deezer",
                    url=deezer_url
                ),

                InlineKeyboardButton(
                    "Apple Music",
                    url=apple_music_url
                )
            ]
        ])

        # =========================
        # COVER
        # =========================

        if cover_url:

            image_response = requests.get(
                cover_url,
                timeout=15
            )

            image_data = image_response.content

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

                await update.message.reply_document(
                    document=InputFile(
                        photo,
                        filename=filename
                    ),
                    caption=caption,
                    reply_markup=keyboard
                )

            os.remove(filename)

        else:

            await update.message.reply_text(
                caption,
                reply_markup=keyboard
            )

    except Exception as e:

        print(e)

        await update.message.reply_text(
            f"Error:\n{e}"
        )

# =========================
# MAIN
# =========================

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

    print("Bot started.")

    app.run_polling()


if __name__ == "__main__":
    main()