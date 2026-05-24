# spotify_parser.py

import re


def extract_spotify_album_id(url):

    match = re.search(
        r"album/([a-zA-Z0-9]+)",
        url
    )

    if not match:
        raise Exception(
            "Invalid Spotify album link."
        )

    return match.group(1)