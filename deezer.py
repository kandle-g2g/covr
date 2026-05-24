import requests


def get_all_tracks(tracklist_url):

    all_tracks = []

    url = tracklist_url

    while url:

        response = requests.get(url)

        data = response.json()

        all_tracks.extend(
            data.get("data", [])
        )

        url = data.get("next")

    return all_tracks


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

    album_data = album_response.json()

    # Получаем ВСЕ треки
    album_data["full_tracks"] = (
        get_all_tracks(
            album_data["tracklist"]
        )
    )

    return album_data