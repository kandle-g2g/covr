# parsers.py

import requests
import re
import json


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def clean_text(text):
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_spotify_metadata(url: str):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=20
    )

    if response.status_code != 200:
        raise Exception("Spotify link open failed")

    html = response.text

    match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        html,
        re.DOTALL
    )

    if not match:
        raise Exception("Spotify metadata not found")

    data = json.loads(match.group(1))

    album_name = clean_text(data.get("name"))

    artists = []

    by_artist = data.get("byArtist")

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


def parse_music_url(url: str):

    if "spotify.com" in url:
        return extract_spotify_metadata(url)

    raise Exception("Unsupported link")