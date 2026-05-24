import requests
from bs4 import BeautifulSoup


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

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    album_name = None
    artists = None
    cover = None

    # =========================
    # COVER
    # =========================

    og_image = soup.find(
        "meta",
        property="og:image"
    )

    if og_image:
        cover = og_image.get("content")

    # =========================
    # TITLE
    # =========================

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
        raw_title = og_title.get("content")

    elif twitter_title:
        raw_title = twitter_title.get("content")

    else:
        raw_title = page_title

    raw_title = raw_title or ""

    # =========================
    # SPOTIFY
    # =========================

    if "spotify.com" in url:

        # Donda (Deluxe) - Album by Kanye West | Spotify

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

        # Album Name by Artist on Apple Music

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

    # =========================
    # FALLBACK
    # =========================

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

    print("PARSED METADATA:", result)

    return result