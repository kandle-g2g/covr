# deezer.py

import requests


def get_album_data(album_id):

    search_url = (
        "https://api.deezer.com/search/album"
    )

    params = {
        "q": album_id
    }

    response = requests.get(
        search_url,
        params=params
    )

    data = response.json()

    albums = data.get("data")

    if not albums:
        return None

    album_api = albums[0]["link"]

    deezer_album_id = (
        albums[0]["id"]
    )

    album_url = (
        f"https://api.deezer.com/album/"
        f"{deezer_album_id}"
    )

    album_response = requests.get(
        album_url
    )

    return album_response.json()