
import re
import requests
from bs4 import BeautifulSoup


def _fetch_soup(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
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

    return BeautifulSoup(response.text, "html.parser")


def _extract_album_artist_from_soup(soup):

    candidates = []

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        candidates.append(og_title["content"])

    twitter_title = soup.find(
        "meta",
        attrs={"name": "twitter:title"}
    )

    if twitter_title and twitter_title.get("content"):
        candidates.append(twitter_title["content"])

    title_tag = soup.find("title")
    if title_tag:
        candidates.append(title_tag.get_text(strip=True))

    for raw in candidates:

        text = raw.strip()

        garbage = [
            " | Spotify",
            " - Spotify",
            " | Apple Music",
            " - Apple Music",
            " | TIDAL",
            " - TIDAL",
            " | Deezer",
            " - Deezer",
            " | YouTube Music",
            " - YouTube Music",
            " | SoundCloud",
            " - SoundCloud",
        ]

        for g in garbage:
            text = text.replace(g, "")

        # Spotify
        if " - Album by " in text:
            album, artist = text.split(" - Album by ", 1)
            return album.strip(), artist.strip()

        separators = [
            " — ",
            " – ",
            " - ",
            " | ",
            " by "
        ]

        for sep in separators:
            if sep in text:
                parts = text.split(sep, 1)

                album = parts[0].strip()
                artist = parts[1].strip()

                if album:
                    return album, artist

        if text:
            return text, None

    return None, None


def _get_cover(soup):

    og_image = soup.find("meta", property="og:image")

    if og_image and og_image.get("content"):
        return og_image["content"]

    twitter_image = soup.find(
        "meta",
        attrs={"name": "twitter:image"}
    )

    if twitter_image and twitter_image.get("content"):
        return twitter_image["content"]

    return None


def extract_album_info_from_url(url):

    soup = _fetch_soup(url)

    album, artist = _extract_album_artist_from_soup(soup)

    if not album:
        raise ValueError("Не удалось получить название альбома")

    return {
        "album_name": album,
        "artists": artist or "Unknown Artist",
        "cover": _get_cover(soup)
    }