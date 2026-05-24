import requests
from bs4 import BeautifulSoup
import re


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