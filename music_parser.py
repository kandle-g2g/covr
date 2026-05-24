import requests
from bs4 import BeautifulSoup
import re


def extract_title_from_page(url):

    response = requests.get(url)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title = soup.find("title")

    if not title:
        return None

    text = title.text

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