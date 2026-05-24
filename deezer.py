import requests


def get_all_tracks(tracklist_url):

    all_tracks = []

    url = tracklist_url

    while url:

        response = requests.get(
            url,
            timeout=15
        )

        data = response.json()

        all_tracks.extend(
            data.get("data", [])
        )

        url = data.get("next")

    return all_tracks


def get_album_by_id(album_id):

    response = requests.get(
        f"https://api.deezer.com/album/{album_id}",
        timeout=15
    )

    album = response.json()

    album["full_tracks"] = (
        get_all_tracks(
            album["tracklist"]
        )
    )

    return album


def search_album(query):

    response = requests.get(
        "https://api.deezer.com/search/album",
        params={
            "q": query
        },
        timeout=15
    )

    data = response.json()

    albums = data.get("data")

    if not albums:
        return None

    album_id = albums[0]["id"]

    return get_album_by_id(album_id)


def search_artist(query):

    response = requests.get(
        "https://api.deezer.com/search/artist",
        params={
            "q": query
        },
        timeout=15
    )

    data = response.json()

    artists = data.get("data")

    if not artists:
        return None

    return artists[0]


def get_artist_albums(artist_id):

    response = requests.get(
        f"https://api.deezer.com/artist/{artist_id}/albums",
        timeout=15
    )

    data = response.json()

    return data.get("data", [])