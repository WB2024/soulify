import re

def clean_special_chars(query):
    # Check if the query contains a hyphen and split only if it does
    if '-' in query:
        query = query.split('-', 1)[0]  # Split at the first hyphen and keep the part before it
    # Remove any trailing or leading spaces
    query = query.strip()
    # Remove all non-alphanumeric characters except spaces
    return re.sub(r'[^a-zA-Z0-9\s]', '', query)

def construct_track_download_command(sldlPath, sldlConfigPath, artistName, trackName):
    """Constructs command for downloading a specific track."""
    cleaned_artist_name = clean_special_chars(artistName)
    cleaned_track_name = clean_special_chars(trackName)
    return f'"{sldlPath}" "{cleaned_artist_name} - {cleaned_track_name}" --config "{sldlConfigPath}"'

def construct_album_download_command(sldlPath, sldlConfigPath, artistName, albumName):
    cleaned_artist_name = clean_special_chars(artistName)
    cleaned_album_name = clean_special_chars(albumName)
    return f'"{sldlPath}" "{cleaned_artist_name} - {cleaned_album_name}" --album --config "{sldlConfigPath}"'

def construct_artist_download_command(sldlPath, sldlConfigPath, artistName):
    cleaned_artist_name = clean_special_chars(artistName)
    return f'"{sldlPath}" "{cleaned_artist_name}" --aggregate --config "{sldlConfigPath}"'

def construct_playlist_download_command(sldlPath, sldlConfigPath, playlistID):
    """Constructs command for downloading a Spotify playlist using the playlist URL."""
    return f'"{sldlPath}" "https://open.spotify.com/playlist/{playlistID}" --config "{sldlConfigPath}" --no-remove-special-chars'
