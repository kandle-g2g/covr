import requests
import re


def clean_query(text):
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\[.*?\]", "", text)
    text = text.replace("Album", "")
    text = text.replace("Spotify", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_music_url(url: str):

    # =========================
    # SPOTIFY
    # =========================
    if "spotify.com/album/" in url:

        response = requests.get(
            "https://open.spotify.com/oembed",
            params={"url": url},
            timeout=10
        )

        if response.status_code != 200:
            raise Exception("Spotify metadata not found")

        data = response.json()

        title = data.get("title", "")
        author = data.get("author_name", "")

        if " - " in title:
            artist, album = title.split(" - ", 1)
        else:
            artist = author
            album = title

        return {
            "album_name": clean_query(album),
            "artists": clean_query(artist),
            "cover": data.get("thumbnail_url")
        }

    # =========================
    # DEEZER
    # =========================
    elif "deezer.com" in url:

        match = re.search(r"/album/(\d+)", url)

        if not match:
            raise Exception("Invalid Deezer link")

        album_id = match.group(1)

        response = requests.get(
            f"https://api.deezer.com/album/{album_id}",
            timeout=10
        )

        if response.status_code != 200:
            raise Exception("Deezer API error")

        data = response.json()

        artists = []

        if "contributors" in data:
            artists = [a["name"] for a in data["contributors"]]

        if not artists and "artist" in data:
            artists = [data["artist"]["name"]]

        return {
            "album_name": clean_query(data["title"]),
            "artists": clean_query(", ".join(artists)),
            "cover": data.get("cover_xl")
        }

    # =========================
    # APPLE MUSIC
    # =========================
    elif "music.apple.com" in url:

        page = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        ).text

        match = re.search(
            r"<title>(.*?)</title>",
            page,
            re.IGNORECASE
        )

        if not match:
            raise Exception("Apple Music metadata not found")

        title = match.group(1)

        title = title.replace(" - Apple Music", "")

        if " by " in title:
            album, artist = title.split(" by ", 1)
        else:
            album = title
            artist = ""

        return {
            "album_name": clean_query(album),
            "artists": clean_query(artist),
            "cover": None
        }

    raise Exception("Unsupported link")