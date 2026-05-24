import requests


def search_album(album_name):

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