import re
import requests
from bs4 import BeautifulSoup

# ------------------------------------------------------------
# Внутренние утилиты
# ------------------------------------------------------------
def _fetch_soup(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")

def _extract_album_artist_from_soup(soup):
    """
    Пытается извлечь (альбом, исполнитель) из метатегов og:title, og:description и title.
    Возвращает (album_name, artist_name) – artist может быть None.
    """
    # 1. og:title
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
        # Разделители: " — ", " – ", " by ", " | "
        for sep in [" — ", " – ", " by ", " | "]:
            if sep in title:
                parts = title.split(sep, 1)
                album = parts[0].strip()
                artist = parts[1].strip() if len(parts) > 1 else None
                return album, artist
        # Если нет разделителя – возможно, только название
        return title, None

    # 2. Обычный <title>
    title_tag = soup.find("title")
    if title_tag:
        raw = title_tag.get_text(strip=True)
        # Удаляем суффиксы платформ
        for suffix in [" - Spotify", " - Apple Music", " | TIDAL", " - YouTube Music", " | SoundCloud", " - Deezer"]:
            raw = raw.replace(suffix, "")
        # Пробуем разделить
        for sep in [" - ", " – ", " | ", " by "]:
            if sep in raw:
                parts = raw.split(sep, 1)
                album = parts[0].strip()
                artist = parts[1].strip() if len(parts) > 1 else None
                return album, artist
        return raw, None

    return None, None

def _get_cover(soup):
    """Извлекает URL обложки из meta og:image или twitter:image"""
    cover = None
    og_image = soup.find("meta", property="og:image")
    if og_image:
        cover = og_image.get("content")
    if not cover:
        twitter_image = soup.find("meta", name="twitter:image")
        if twitter_image:
            cover = twitter_image.get("content")
    return cover

# ------------------------------------------------------------
# Парсеры для конкретных сервисов
# ------------------------------------------------------------
def _parse_spotify(url):
    soup = _fetch_soup(url)
    album, artist = _extract_album_artist_from_soup(soup)
    cover = _get_cover(soup)
    return album, artist, cover

def _parse_deezer(url):
    # Используем Deezer API (ваш deezer.py), так как это точнее
    from deezer import get_album_by_id
    album_id_match = re.search(r"album[/]?(\d+)", url)
    if not album_id_match:
        raise ValueError("Неверная Deezer ссылка")
    album_id = album_id_match.group(1)
    album_data = get_album_by_id(album_id)
    title = album_data["title"]
    # Собираем всех артистов
    artists = []
    if "contributors" in album_data and album_data["contributors"]:
        artists = [a["name"] for a in album_data["contributors"]]
    else:
        artists = [album_data["artist"]["name"]]
    artist_str = ", ".join(dict.fromkeys(artists))
    cover = album_data.get("cover_xl")
    return title, artist_str, cover

def _parse_apple_music(url):
    soup = _fetch_soup(url)
    album, artist = _extract_album_artist_from_soup(soup)
    cover = _get_cover(soup)
    return album, artist, cover

def _parse_tidal(url):
    soup = _fetch_soup(url)
    album, artist = _extract_album_artist_from_soup(soup)
    cover = _get_cover(soup)
    return album, artist, cover

def _parse_youtube_music(url):
    soup = _fetch_soup(url)
    album, artist = _extract_album_artist_from_soup(soup)
    cover = _get_cover(soup)
    return album, artist, cover

def _parse_soundcloud(url):
    # SoundCloud: работаем только с сетами (альбомами)
    if "/sets/" not in url:
        raise ValueError("Поддерживаются только ссылки на плейлисты/альбомы SoundCloud (sets)")
    soup = _fetch_soup(url)
    album, artist = _extract_album_artist_from_soup(soup)
    cover = _get_cover(soup)
    return album, artist, cover

# ------------------------------------------------------------
# Главная функция (внешний интерфейс)
# ------------------------------------------------------------
def extract_album_info_from_url(url: str):
    """
    Определяет музыкальный сервис по URL и возвращает словарь:
    {
        "album_name": str,
        "artists": str,
        "cover": str or None
    }
    """
    domain = url.lower()
    try:
        if "spotify.com/album" in domain:
            album, artist, cover = _parse_spotify(url)
        elif "deezer.com/album" in domain:
            album, artist, cover = _parse_deezer(url)
        elif "music.apple.com" in domain or "itunes.apple.com" in domain:
            album, artist, cover = _parse_apple_music(url)
        elif "tidal.com/browse/album" in domain:
            album, artist, cover = _parse_tidal(url)
        elif "music.youtube.com" in domain or "youtube.com/playlist" in domain or "youtu.be" in domain:
            album, artist, cover = _parse_youtube_music(url)
        elif "soundcloud.com" in domain and "/sets/" in domain:
            album, artist, cover = _parse_soundcloud(url)
        else:
            # Универсальный парсинг для неизвестных ссылок
            soup = _fetch_soup(url)
            album, artist = _extract_album_artist_from_soup(soup)
            cover = _get_cover(soup)
    except Exception as e:
        raise ValueError(f"Не удалось распарсить ссылку: {e}")

    if not album:
        raise ValueError("Не удалось извлечь название альбома")
    if not artist:
        artist = "Unknown Artist"

    return {
        "album_name": album,
        "artists": artist,
        "cover": cover
    }

# ------------------------------------------------------------
# Сохраняем старые функции (для обратной совместимости, если они где-то используются)
# ------------------------------------------------------------
def extract_title_from_page(url):
    try:
        data = extract_album_info_from_url(url)
        return data["album_name"]
    except:
        return None

def extract_deezer_album_id(url):
    match = re.search(r"album/(\d+)", url)
    return match.group(1) if match else None