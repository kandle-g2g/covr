import requests
from bs4 import BeautifulSoup


def extract_album_name(url):

    response = requests.get(url)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title = soup.find("title")

    if not title:
        raise Exception(
            "Could not parse Spotify page."
        )

    text = title.text

    text = text.replace(
        " - Album by ",
        "|"
    )

    album_name = text.split("|")[0].strip()

    return album_name