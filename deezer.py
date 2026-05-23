import requests

def search_album(album_name, artist_name):
    query = f"{album_name} {artist_name}"
    response = requests.get(
        "https://api.deezer.com/search/album",
        params={"q": query}
    )
    if response.status_code != 200:
        raise Exception("Ошибка Deezer API")
    data = response.json()
    if not data["data"]:
        raise Exception("Альбом не найден")
    return data["data"][0]

def get_album_tracks(album_id):
    # 1. Получаем метаданные альбома (название, обложка, дата, артисты)
    response = requests.get(f"https://api.deezer.com/album/{album_id}")
    if response.status_code != 200:
        raise Exception("Ошибка получения альбома")
    data = response.json()

    # 2. Получаем ВСЕ треки через пагинацию (игнорируем встроенные первые 25)
    all_tracks_data = []
    index = 0
    limit = 100
    while True:
        tracks_response = requests.get(
            f"https://api.deezer.com/album/{album_id}/tracks",
            params={"limit": limit, "index": index}
        )
        if tracks_response.status_code != 200:
            break
        tracks_data = tracks_response.json()
        batch = tracks_data.get("data", [])
        if not batch:
            break
        all_tracks_data.extend(batch)
        if len(batch) < limit:
            break  # последняя страница
        index += len(batch)

    # 3. Формируем треклист и общую длительность
    tracks = []
    total_duration = 0
    for track in all_tracks_data:
        total_duration += track.get("duration", 0)
        tracks.append(track.get("title", "Unknown"))

    # 4. Собираем артистов (contributors или основной)
    artists = []
    if "contributors" in data:
        for artist in data["contributors"]:
            name = artist.get("name")
            if name and name not in artists:
                artists.append(name)
    if not artists:
        main_artist = data.get("artist", {}).get("name")
        if main_artist:
            artists.append(main_artist)

    # 5. Форматируем длительность
    hours = total_duration // 3600
    minutes = (total_duration % 3600) // 60
    seconds = total_duration % 60
    if hours > 0:
        formatted_duration = f"{hours}:{minutes:02}:{seconds:02}"
    else:
        formatted_duration = f"{minutes:02}:{seconds:02}"

    # 6. Возвращаем результат
    return {
        "title": data.get("title", "Unknown"),
        "artists": ", ".join(artists),
        "release_date": data.get("release_date", "Unknown"),
        "cover": data.get("cover_xl", ""),
        "tracks": tracks,
        "tracks_count": len(all_tracks_data),
        "total_duration": formatted_duration
    }