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
    # Первый запрос – получаем основную информацию и первую страницу треков
    response = requests.get(f"https://api.deezer.com/album/{album_id}?limit=100")
    if response.status_code != 200:
        raise Exception("Ошибка получения альбома")

    data = response.json()
    total_tracks = data["tracks"]["total"]
    all_tracks_data = data["tracks"]["data"]  # первые треки

    # Пагинация – добираем остальные треки, если их больше 100
    while len(all_tracks_data) < total_tracks:
        next_index = len(all_tracks_data)
        next_response = requests.get(
            f"https://api.deezer.com/album/{album_id}/tracks",
            params={"limit": 100, "index": next_index}
        )
        if next_response.status_code != 200:
            break  # если ошибка – выходим, но уже собранные треки сохраним
        next_data = next_response.json()
        all_tracks_data.extend(next_data["data"])

    # Формируем треклист и общую длительность
    tracks = []
    total_duration = 0
    for track in all_tracks_data:
        total_duration += track.get("duration", 0)
        tracks.append(track['title'])

    # Артисты (без изменений)
    artists = []
    if "contributors" in data:
        for artist in data["contributors"]:
            name = artist.get("name")
            if name and name not in artists:
                artists.append(name)
    if not artists:
        artists.append(data["artist"]["name"])

    # Форматирование длительности
    hours = total_duration // 3600
    minutes = (total_duration % 3600) // 60
    seconds = total_duration % 60
    if hours > 0:
        formatted_duration = f"{hours}:{minutes:02}:{seconds:02}"
    else:
        formatted_duration = f"{minutes:02}:{seconds:02}"

    return {
        "title": data["title"],
        "artists": ", ".join(artists),
        "release_date": data["release_date"],
        "cover": data["cover_xl"],
        "tracks": tracks,
        "tracks_count": len(all_tracks_data),
        "total_duration": formatted_duration
    }