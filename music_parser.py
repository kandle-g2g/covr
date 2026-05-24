import requests
import re
from bs4 import BeautifulSoup

def clean_query(text):
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\[.*?\]", "", text)
    text = text.replace("Album", "")
    text = text.replace("Spotify", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def parse_music_url(url: str):
    # Spotify
    if "spotify.com/album/" in url:
        resp = requests.get("https://open.spotify.com/oembed", params={"url": url}, timeout=10)
        if resp.status_code != 200:
            raise Exception("Spotify oembed failed")
        data = resp.json()
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
    # Deezer (запасной вариант)
    elif "deezer.com/album/" in url:
        match = re.search(r"/album/(\d+)", url)
        if not match:
            raise Exception("Invalid Deezer link")
        album_id = match.group(1)
        resp = requests.get(f"https://api.deezer.com/album/{album_id}", timeout=10)
        data = resp.json()
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
    # Apple Music
    elif "music.apple.com" in url:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        # Пытаемся взять og:title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title_text = og_title["content"]
        else:
            title_tag = soup.find("title")
            title_text = title_tag.string if title_tag else ""
        if not title_text:
            raise Exception("Apple Music title not found")
        # Очищаем
        title_text = re.sub(r"\s*[-|]\s*Apple Music$", "", title_text, flags=re.I)
        if " by " in title_text:
            album, artist = title_text.split(" by ", 1)
        elif " – " in title_text:
            album, artist = title_text.split(" – ", 1)
        else:
            album = title_text
            artist = ""
        # Удаляем " on Apple Music" и подобное
        artist = re.sub(r"\s+on Apple Music$", "", artist, flags=re.I)
        artist = re.sub(r"on Apple Music$", "", artist, flags=re.I).strip()
        return {
            "album_name": clean_query(album),
            "artists": clean_query(artist),
            "cover": None
        }
    raise Exception("Unsupported link")