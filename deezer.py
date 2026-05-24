# deezer.py

import requests


def get_spotify_album_info(url):

    oembed_url = (
        "https://open.spotify.com/oembed"
    )

    response = requests.get(
        oembed_url,
        params={
            "url": url
        }
    )

    if response.status_code != 200:
        return None

    return response.json()


def search_deezer_album(album_name):

    response = requests.get(
        "https://api.deezer.com/search/album",
        params={
            "q": album_name
        }
    )

    data = response.json()

    albums = data.get("data")

    if not albums:
        return None

    album_id = albums[0]["id"]

    album_response = requests.get(
        f"https://api.deezer.com/album/{album_id}"
    )

    return album_response.json()