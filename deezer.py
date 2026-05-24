import requests

def search_album(album_name, artist_name=""):
    query = f"{artist_name} {album_name}".strip()
    response = requests.get(
        "https://api.deezer.com/search/album",
        params={"q": query},
        timeout=10
    )
    if response.status_code != 200:
        raise Exception("Deezer API error")
    data = response.json()
    if not data.get("data"):
        raise Exception("Album not found")
    return data["data"][0]

def search_artist(artist_name):
    response = requests.get(
        "https://api.deezer.com/search/artist",
        params={"q": artist_name},
        timeout=10
    )
    if response.status_code != 200:
        return None
    data = response.json()
    artists = data.get("data", [])
    if not artists:
        return None
    return artists[0]

def search_artist_albums(artist_name):
    artist = search_artist(artist_name)
    if not artist:
        return []
    artist_id = artist["id"]
    albums_response = requests.get(
        f"https://api.deezer.com/artist/{artist_id}/albums",
        timeout=10
    )
    if albums_response.status_code != 200:
        return []
    albums = albums_response.json().get("data", [])
    unique = []
    seen = set()
    for album in albums:
        title = album["title"]
        if title in seen:
            continue
        seen.add(title)
        unique.append(album)
    return unique[:20]

def get_album_tracks(album_id):
    response = requests.get(
        f"https://api.deezer.com/album/{album_id}",
        timeout=10
    )
    if response.status_code != 200:
        raise Exception("Album fetch error")
    data = response.json()
    tracks = []
    total_duration = 0
    all_artists = []
    if "contributors" in data:
        all_artists = [a["name"] for a in data["contributors"]]
    if not all_artists:
        all_artists = [data["artist"]["name"]]
    tracklist_url = data.get("tracklist")
    while tracklist_url:
        track_response = requests.get(tracklist_url, timeout=10)
        track_data = track_response.json()
        for track in track_data["data"]:
            tracks.append(track["title"])
            total_duration += track.get("duration", 0)
        tracklist_url = track_data.get("next")
    hours = total_duration // 3600
    minutes = (total_duration % 3600) // 60
    seconds = total_duration % 60
    if hours > 0:
        duration_text = f"{hours}:{minutes:02}:{seconds:02}"
    else:
        duration_text = f"{minutes}:{seconds:02}"
    return {
        "id": data["id"],
        "title": data["title"],
        "artist": ", ".join(all_artists),
        "release_date": data["release_date"],
        "cover": data["cover_xl"],
        "tracks": tracks,
        "track_count": len(tracks),
        "duration": duration_text,
        "link": data["link"]
    }