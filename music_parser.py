import requests
from bs4 import BeautifulSoup
import re
import json


def clean_text(text):

    if not text:
        return ""

    garbage = [
        "| Spotify",
        "- Spotify",
        "| Apple Music",
        "- Apple Music",
        "| Deezer",
        "- Deezer",
        "| TIDAL",
        "- TIDAL",
        "| YouTube Music",
        "- YouTube Music",
        "| SoundCloud",
        "- SoundCloud",
        "on Apple Music",
    ]

    for g in garbage:
        text = text.replace(g, "")

    return text.strip()


def extract_spotify_jsonld(html):

    match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        html,
        re.DOTALL
    )

    if not match:
        return None

    try:
        data = json.loads(
            match.group(1)
        )

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

        cover = data.get("image")

        return {
            "album_name": album_name,
            "artists": ", ".join(artists),
            "cover": cover
        }

    except Exception:
        return None


def extract_album_info_from_url(url):

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=20,
        allow_redirects=True
    )

    response.raise_for_status()

    html = response.text

    # =========================
    # SPOTIFY JSON-LD
    # =========================

    if "spotify.com" in url:

        parsed = extract_spotify_jsonld(
            html
        )

        if parsed:

            print(
                "SPOTIFY JSON-LD:",
                parsed
            )

            return parsed

    # =========================
    # FALLBACK HTML PARSER
    # =========================

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    album_name = None
    artists = None
    cover = None

    og_image = soup.find(
        "meta",
        property="og:image"
    )

    if og_image:
        cover = og_image.get(
            "content"
        )

    og_title = soup.find(
        "meta",
        property="og:title"
    )

    twitter_title = soup.find(
        "meta",
        attrs={"name": "twitter:title"}
    )

    page_title = (
        soup.title.string
        if soup.title
        else ""
    )

    raw_title = None

    if og_title:
        raw_title = og_title.get(
            "content"
        )

    elif twitter_title:
        raw_title = twitter_title.get(
            "content"
        )

    else:
        raw_title = page_title

    raw_title = raw_title or ""

    # =========================
    # SPOTIFY FALLBACK
    # =========================

    if "spotify.com" in url:

        if " - Album by " in raw_title:

            parts = raw_title.split(
                " - Album by ",
                1
            )

            album_name = parts[0].strip()

            artists = clean_text(
                parts[1]
            )

        elif " - Single by " in raw_title:

            parts = raw_title.split(
                " - Single by ",
                1
            )

            album_name = parts[0].strip()

            artists = clean_text(
                parts[1]
            )

        elif " - EP by " in raw_title:

            parts = raw_title.split(
                " - EP by ",
                1
            )

            album_name = parts[0].strip()

            artists = clean_text(
                parts[1]
            )

        else:
            album_name = clean_text(
                raw_title
            )

    # =========================
    # APPLE MUSIC
    # =========================

    elif "music.apple.com" in url:

        if " by " in raw_title:

            parts = raw_title.split(
                " by ",
                1
            )

            album_name = parts[0].strip()

            artists = clean_text(
                parts[1]
            )

        else:
            album_name = clean_text(
                raw_title
            )

    # =========================
    # DEEZER
    # =========================

    elif "deezer.com" in url:

        album_name = clean_text(
            raw_title
        )

        artist_meta = soup.find(
            "meta",
            property="music:musician_description"
        )

        if artist_meta:
            artists = artist_meta.get(
                "content"
            )

    else:

        album_name = clean_text(
            raw_title
        )

    if not album_name:
        album_name = "Unknown Album"

    if not artists:
        artists = "Unknown Artist"

    result = {
        "album_name": album_name,
        "artists": artists,
        "cover": cover
    }

    print(
        "FALLBACK PARSED:",
        result
    )

    return result