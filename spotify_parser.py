import requests
from bs4 import BeautifulSoup
import re
import json


def extract_spotify_metadata(url: str):

    headers = {
        "User-Agent": (
            "Mozilla/5.0"
        )
    }

    response = requests.get(
        url,
        headers=headers
    )

    if response.status_code != 200:
        raise Exception(
            "Не удалось открыть Spotify ссылку"
        )

    html = response.text

    # Ищем JSON-LD metadata
    match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        html,
        re.DOTALL
    )

    if not match:
        raise Exception(
            "Не удалось получить metadata"
        )

    data = json.loads(
        match.group(1)
    )

    # Название альбома
    album_name = data.get(
        "name",
        "Unknown Album"
    )

    # Артисты
    artists = []

    by_artist = data.get("byArtist")

    # Если список артистов
    if isinstance(by_artist, list):

        for artist in by_artist:

            if isinstance(artist, dict):

                name = artist.get("name")

                if name:
                    artists.append(name)

    # Если один артист
    elif isinstance(by_artist, dict):

        name = by_artist.get("name")

        if name:
            artists.append(name)

    # Если Spotify отдал пусто
    if not artists:

        # Пытаемся достать из title страницы
        title_match = re.search(
            r"<title>(.*?)</title>",
            html
        )

        if title_match:

            title_text = title_match.group(1)

            # Обычно:
            # "Album Name - Album by Artist | Spotify"
            parts = title_text.split(" - Album by ")

            if len(parts) > 1:

                artist_part = parts[1]

                artist_part = artist_part.replace(
                    " | Spotify",
                    ""
                )

                artists.append(
                    artist_part
                )

    # Финальный список артистов
    artists_string = ", ".join(artists)

    # Обложка
    cover = data.get("image")

    return {
        "album_name": album_name,
        "artists": artists_string,
        "cover": cover
    }