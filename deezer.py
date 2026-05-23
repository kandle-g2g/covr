import requests


def search_album(album_name, artist_name):

    query = f"{album_name} {artist_name}"

    response = requests.get(
        "https://api.deezer.com/search/album",
        params={
            "q": query
        }
    )

    if response.status_code != 200:
        raise Exception(
            "Ошибка Deezer API"
        )

    data = response.json()

    if not data["data"]:
        raise Exception(
            "Альбом не найден"
        )

    return data["data"][0]


def get_album_tracks(album_id):

    response = requests.get(
        f"https://api.deezer.com/album/{album_id}"
    )

    if response.status_code != 200:
        raise Exception(
            "Ошибка получения альбома"
        )

    data = response.json()

    all_tracks = data["tracks"]["data"]

    tracks = []

    total_duration = 0

    # Треки
    for track in all_tracks:

        total_duration += track.get(
            "duration",
            0
        )

        tracks.append(
            track['title']
        )

    # Все артисты
    artists = []

    if "contributors" in data:

        for artist in data["contributors"]:

            name = artist.get("name")

            if (
                name
                and name not in artists
            ):
                artists.append(name)

    # fallback
    if not artists:

        artists.append(
            data["artist"]["name"]
        )

    # Форматируем длительность
    hours = total_duration // 3600

    minutes = (
        total_duration % 3600
    ) // 60

    seconds = total_duration % 60

    # Формат:
    # 45:12
    # 1:04:09

    if hours > 0:

        formatted_duration = (
            f"{hours}:"
            f"{minutes:02}:"
            f"{seconds:02}"
        )

    else:

        formatted_duration = (
            f"{minutes:02}:"
            f"{seconds:02}"
        )

    return {
        "title": data["title"],
        "artists": ", ".join(artists),
        "release_date": data["release_date"],
        "cover": data["cover_xl"],
        "tracks": tracks,
        "tracks_count": len(all_tracks),
        "total_duration": formatted_duration
    }