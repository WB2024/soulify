from flask import Flask, redirect, request, session, url_for, render_template, jsonify, Response, stream_with_context
from CommandConstruct import (construct_track_download_command,
                              construct_album_download_command,
                              construct_artist_download_command,
                              construct_playlist_download_command)
from datetime import datetime
import requests
import base64
import urllib.parse
import os
import subprocess
import logging
import time
import uuid
import configparser
import shlex
from threading import Thread
import re


app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Path to configuration and post-processing scripts
base_dir = os.path.dirname(os.path.abspath(__file__))
soulify_conf_path = os.path.join(base_dir, 'soulify.conf')
postdownload_scripts_dir = os.path.join(base_dir, 'scripts', 'postdownload')
run_all_script = os.path.join(postdownload_scripts_dir, 'RunAll.py')
sort_move_music_script = os.path.join(postdownload_scripts_dir, 'Sort_MoveMusicDownloads.py')
update_with_mb_script = os.path.join(postdownload_scripts_dir, 'UpdatewithMB.sh')
pdscript_conf_path = os.path.join(base_dir, 'pdscript.conf')

# Function to read the soulify.conf file
def read_soulify_conf():
    config = configparser.ConfigParser()
    config.read(soulify_conf_path)
    try:
        update_with_mb = config.getboolean('PostDownloadProcessing', 'UpdatemetadataWithMusicBrainz', fallback=False)
        update_library = config.getboolean('PostDownloadProcessing', 'UpdateLibraryMetadataAndRefreshJellyfin', fallback=False)
        return update_with_mb, update_library
    except configparser.Error as e:
        logging.error(f"Error reading configuration: {e}")
        return False, False  # Fallback to False if there's an error
        
# Function to write soulify.conf (missing in original code)
def write_soulify_conf(settings):
    config = configparser.ConfigParser()
    config['PostDownloadProcessing'] = {
        'UpdatemetadataWithMusicBrainz': str(settings['UpdatemetadataWithMusicBrainz']),
        'UpdateLibraryMetadataAndRefreshJellyfin': str(settings['UpdateLibraryMetadataAndRefreshJellyfin'])
    }
    try:
        with open(soulify_conf_path, 'w') as configfile:
            config.write(configfile)
    except IOError as e:
        logging.error(f"Error writing to soulify.conf: {e}")

# Function to write sldl.conf
def write_sldl_conf(settings):
    try:
        with open(sldlConfigPath, 'w') as f:
            f.write("# Soulseek Credentials (required)\n")
            f.write(f"username = {settings.get('username', '')}\n")
            f.write(f"password = {settings.get('password', '')}\n")
            f.write("\n# General Download Settings\n")
            f.write(f"path = {settings.get('path', '')}\n")
            f.write("\n# Search Settings\n")
            f.write(f"no-remove-special-chars = {settings.get('no-remove-special-chars', 'false')}\n")
            f.write("\n# Preferred File Conditions\n")
            f.write(f"pref-format = {settings.get('pref-format', '')}\n")
            f.write("\n# Spotify Settings\n")
            f.write(f"spotify-id = {settings.get('spotify-id', '')}\n")
            f.write(f"spotify-secret = {settings.get('spotify-secret', '')}\n")
            f.write("\n# Output Settings\n")
            f.write(f"m3u = {settings.get('m3u', 'none')}\n")
    except IOError as e:
        logging.error(f"Error writing to sldl.conf: {e}")
        
# Function to read pdscript.conf
def read_pdscript_conf():
    config = configparser.ConfigParser()
    config.read(pdscript_conf_path)
    try:
        destination_root = config.get('Paths', 'destination_root', fallback='/mnt/EXTHDD/Media/Audio/Music/Music - Managed (Lidarr)/')
        new_artists_dir = config.get('Paths', 'new_artists_dir', fallback='/mnt/EXTHDD/Download/Music New Artists/')
        api_base_url = config.get('API Details', 'API_BASE_URL', fallback='http://192.168.0.7:8096')
        api_auth_token = config.get('API Details', 'API_AUTH_TOKEN', fallback='b30092879a9646eb9e676b2922c9c1e4')
        return {
            'destination_root': destination_root,
            'new_artists_dir': new_artists_dir,
            'API_BASE_URL': api_base_url,
            'API_AUTH_TOKEN': api_auth_token
        }
    except configparser.Error as e:
        logging.error(f"Error reading pdscript.conf: {e}")
        return {}

# Function to write pdscript.conf
def write_pdscript_conf(settings):
    config = configparser.ConfigParser()
    config['Paths'] = {
        'destination_root': settings.get('destination_root', '/mnt/EXTHDD/Media/Audio/Music/Music - Managed (Lidarr)/'),
        'new_artists_dir': settings.get('new_artists_dir', '/mnt/EXTHDD/Download/Music New Artists/')
    }
    config['API Details'] = {
        'API_BASE_URL': settings.get('API_BASE_URL', 'http://192.168.0.7:8096'),
        'API_AUTH_TOKEN': settings.get('API_AUTH_TOKEN', 'b30092879a9646eb9e676b2922c9c1e4')
    }
    try:
        with open(pdscript_conf_path, 'w') as configfile:
            config.write(configfile)
    except IOError as e:
        logging.error(f"Error writing to pdscript.conf: {e}")

def clean_special_chars(query):
    # First remove all commas
    query = query.replace(',', '')
    # Then remove all other special characters except for alphanumeric, spaces, and hyphens
    return re.sub(r'[^a-zA-Z0-9\s\-]', '', query)


# Function to execute post-processing scripts based on the configuration
def run_post_processing():
    update_with_mb, update_library = read_soulify_conf()

    # Check conditions and run the appropriate scripts
    if update_library and update_with_mb:
        # Run RunAll.py
        logging.info("Running RunAll.py script...")
        result = subprocess.run(['python3', run_all_script], capture_output=True, text=True)
        log_post_processing_output(result, 'RunAll.py')
    elif update_library and not update_with_mb:
        # Run Sort_MoveMusicDownloads.py
        logging.info("Running Sort_MoveMusicDownloads.py script...")
        result = subprocess.run(['python3', sort_move_music_script], capture_output=True, text=True)
        log_post_processing_output(result, 'Sort_MoveMusicDownloads.py')
    elif update_with_mb and not update_library:
        # Run UpdatewithMB.sh
        logging.info("Running UpdatewithMB.sh script...")
        result = subprocess.run(['bash', update_with_mb_script], capture_output=True, text=True)
        log_post_processing_output(result, 'UpdatewithMB.sh')
    else:
        # No post-processing needed
        logging.info("No post-processing scripts to run.")

# Function to log the output of post-processing scripts
def log_post_processing_output(result, script_name):
    # Log the output of the post-processing script
    with open('CurrentCommandLog', 'a') as log_file:
        log_file.write(f"Post-processing script: {script_name}\n")
        log_file.write(f"Output: {result.stdout}\n")
        log_file.write(f"Error: {result.stderr}\n")

# Clear the contents of the command-related files
def initialize_files():
    files_to_clear = ['CurrentCommand', 'CommandQueue', 'CurrentCommandLog']
    for file_name in files_to_clear:
        try:
            open(file_name, 'w').close()  # This clears the file
        except IOError as e:
            logging.error(f"Error initializing file {file_name}: {e}")

    # Ensure CommandHistory exists
    if not os.path.exists('CommandHistory'):
        try:
            open('CommandHistory', 'w').close()
        except IOError as e:
            logging.error(f"Error creating CommandHistory: {e}")

# Call initialize_files when the app starts
initialize_files()

# Load the Spotify settings from sldl.conf
def parse_sldl_conf(file_path):
    spotify_settings = {}
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                key_value = line.split('=', 1)
                if len(key_value) == 2:
                    key, value = key_value[0].strip(), key_value[1].strip()
                    spotify_settings[key] = value
    except IOError as e:
        logging.error(f"Error reading config file {file_path}: {e}")
    return spotify_settings

# Dynamically construct the paths based on the location of SpotWebApp.py
base_dir = os.path.dirname(os.path.abspath(__file__))
sldlPath = os.path.join(base_dir, 'sldl')
sldlConfigPath = os.path.join(base_dir, 'sldl.conf')

# Now that parse_sldl_conf is defined, you can call it
spotify_config = parse_sldl_conf(sldlConfigPath)
CLIENT_ID = spotify_config.get('spotify-id')
CLIENT_SECRET = spotify_config.get('spotify-secret')
REDIRECT_URI = spotify_config.get('redirect-uri')

# Spotify API URLs and scope
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SCOPE = "user-read-private user-read-email playlist-read-private playlist-read-collaborative"

# Ensure valid token
def ensure_valid_token():
    """Ensure that the Spotify access token is valid or refresh if needed."""
    access_token = session.get('access_token')
    if not access_token:
        return redirect(url_for('login'))

    response = requests.get('https://api.spotify.com/v1/me', headers={'Authorization': f'Bearer {access_token}'})
    if response.status_code == 401:  # Token has expired
        if refresh_spotify_token():
            access_token = session.get('access_token')
        else:
            return redirect(url_for('login'))
    return access_token

def refresh_spotify_token():
    """Utility to refresh the Spotify access token."""
    refresh_token = session.get('refresh_token')
    headers = {
        'Authorization': 'Basic ' + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode(),
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    response = requests.post(SPOTIFY_TOKEN_URL, headers=headers, data=data)
    if response.status_code == 200:
        token_data = response.json()
        session['access_token'] = token_data['access_token']
        session['refresh_token'] = token_data.get('refresh_token', refresh_token)  # Keep old refresh token if none is provided
        return True
    return False  # If refresh fails

@app.route('/')
def index():
    """Home route."""
    access_token = ensure_valid_token()  # Check for valid token and refresh if needed
    if not access_token:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/playlists')
def playlists():
    """List the user's Spotify playlists."""
    access_token = ensure_valid_token()
    if not access_token:
        return redirect(url_for('login'))

    headers = {'Authorization': f'Bearer {access_token}'}
    url = "https://api.spotify.com/v1/me/playlists?limit=50&offset=0"
    playlists = []
    while url:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            playlists.extend(data['items'])
            url = data['next']  # Next page URL
        else:
            return f"Error fetching playlists: {response.json()}"

    return render_template('playlist.html', playlists=playlists)

@app.route('/playlisttracks/<playlist_id>')
def playlist_tracks(playlist_id):
    """View tracks from a specific playlist."""
    access_token = ensure_valid_token()
    if not access_token:
        return redirect(url_for('login'))

    playlist_name = request.args.get('playlist_name')
    headers = {'Authorization': f'Bearer {access_token}'}
    url = f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks?limit=100'
    tracks = []
    while url:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            tracks.extend(data['items'])
            url = data['next']
        else:
            return f"Error fetching playlist tracks: {response.json()}"

    return render_template('playlisttracks.html', tracks=tracks, playlist_name=playlist_name)

@app.route('/search', methods=['GET', 'POST'])
def search():
    """Search for artists, albums, or tracks."""
    if request.method == 'POST':
        query = request.form.get('search_query')
        search_type = request.form.get('search_type')

        if not query or not search_type:
            return render_template('search.html', error="Please enter a search query and select a search type.")

        access_token = ensure_valid_token()
        if not access_token:
            return redirect(url_for('login'))

        headers = {'Authorization': f'Bearer {access_token}'}
        search_url = f'https://api.spotify.com/v1/search?q={urllib.parse.quote(query)}&type={search_type}'
        response = requests.get(search_url, headers=headers)

        if response.status_code == 200:
            search_results = response.json()
            return render_template('search_results.html', search_results=search_results, search_type=search_type)
        else:
            return f"Error fetching search results: {response.json()}"

    return render_template('search.html')

@app.route('/login')
def login():
    """Spotify login route."""
    auth_url = f"{SPOTIFY_AUTH_URL}?response_type=code&client_id={CLIENT_ID}&scope={urllib.parse.quote(SCOPE)}&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    return redirect(auth_url)

@app.route('/logout')
def logout():
    """Logout route."""
    session.clear()  # Clear session tokens
    return redirect(url_for('login'))

@app.route('/callback')
def callback():
    """Spotify authorization callback."""
    code = request.args.get('code')
    if not code:
        return "Authorization failed."

    token_response = requests.post(
        SPOTIFY_TOKEN_URL,
        data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        },
        headers={
            'Authorization': 'Basic ' + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode(),
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    )

    if token_response.status_code != 200:
        return f"Error fetching access token: {token_response.json()}"

    token_data = token_response.json()
    session['access_token'] = token_data.get('access_token')
    session['refresh_token'] = token_data.get('refresh_token')

    return redirect(url_for('index'))

@app.route('/refresh_token')
def refresh_token():
    """Refresh the Spotify access token."""
    if refresh_spotify_token():
        return redirect(url_for('index'))
    else:
        return "Failed to refresh token, please log in again."
        
@app.route('/download_track', methods=['POST'])
def download_track():
    data = request.json
    command = construct_track_download_command(sldlPath, sldlConfigPath, data['artistName'], data['name'])
    
    # Queue the command instead of executing it directly
    queue_command(command)
    
    return jsonify({'status': 'queued', 'command': command, 'data': data}), 200

@app.route('/download_album', methods=['POST'])
def download_album():
    data = request.json
    command = construct_album_download_command(sldlPath, sldlConfigPath, data['artistName'], data['name'])
    
    # Queue the command
    queue_command(command)

    return jsonify({'status': 'queued', 'command': command}), 200

@app.route('/download_artist', methods=['POST'])
def download_artist():
    data = request.json
    command = construct_artist_download_command(sldlPath, sldlConfigPath, data['artistName'])
    
    # Queue the command
    queue_command(command)
    
    return jsonify({'status': 'queued', 'command': command}), 200

@app.route('/download_playlist', methods=['POST'])
def download_playlist():
    data = request.get_json()
    playlist_id = data.get('playlist_id')
    
    if not playlist_id:
        return jsonify({'status': 'error', 'message': 'Missing playlist ID'}), 400
    
    try:
        command = construct_playlist_download_command(sldlPath, sldlConfigPath, playlist_id)
        queue_command(command)
        return jsonify({'status': 'queued', 'command': command, 'data': {'playlist_id': playlist_id}}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# Add a command to the CommandQueue
def queue_command(command):
    command_id = str(uuid.uuid4())  # Unique command ID
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    command_entry = f"{command_id},{timestamp},{command}\n"
    
    try:
        with open('CommandQueue', 'a') as queue_file:
            queue_file.write(command_entry)
    except IOError as e:
        logging.error(f"Error writing to CommandQueue: {e}")

# Get the next command from the CommandQueue (the oldest command)
def get_next_command():
    try:
        with open('CommandQueue', 'r') as queue_file:
            lines = queue_file.readlines()
    except IOError as e:
        logging.error(f"Error reading from CommandQueue: {e}")
        return None

    if not lines:
        return None  # No commands in the queue

    # Get the oldest command (first in the list)
    next_command = lines[0]
    
    # Remove the oldest command from the queue
    try:
        with open('CommandQueue', 'w') as queue_file:
            queue_file.writelines(lines[1:])
    except IOError as e:
        logging.error(f"Error updating CommandQueue: {e}")

    if len(next_command.split(',', 2)) < 3:
        logging.error(f"Malformed command in queue: {next_command}")
        return None

    return next_command.strip()

# Function to execute commands in a loop
def execute_command_loop():
    while True:
        # Check if there's a current command running
        if not os.path.exists('CurrentCommand') or os.stat('CurrentCommand').st_size == 0:
            next_command = get_next_command()
            
            if next_command:
                try:
                    # Write the next command to CurrentCommand
                    command_id, timestamp, command = next_command.split(',', 2)
                    with open('CurrentCommand', 'w') as current_file:
                        current_file.write(f"{command_id},{timestamp},{command}\n")

                    # Log the command before execution
                    logging.info(f"Executing command: {command}")

                    # Use shlex.split to safely split the command and handle special characters
                    command_list = shlex.split(command)
                    
                    # Execute the command
                    try:
                        result = subprocess.run(command_list, capture_output=True, text=True, check=True)
                    except subprocess.CalledProcessError as e:
                        result = e  # Capture the exception and treat it like a result

                    # Log the output to CurrentCommandLog
                    with open('CurrentCommandLog', 'w') as log_file:
                        log_file.write(f"Command: {command}\nOutput: {result.stdout}\nError: {result.stderr}\n")

                    # Append the command and output to CommandHistory
                    with open('CommandHistory', 'a') as history_file:
                        with open('CurrentCommandLog', 'r') as log_file:
                            history_file.write(log_file.read())

                    # Run the post-processing step based on the configuration
                    run_post_processing()

                except IOError as e:
                    logging.error(f"Error handling command execution: {e}")

                # Clear CurrentCommand and CurrentCommandLog after completion
                open('CurrentCommand', 'w').close()
                open('CurrentCommandLog', 'w').close()

        else:
            # If there's a current command, wait for it to finish
            time.sleep(3)
@app.route('/Download_Current')
def download_current():
    current_command = ""
    current_log = ""

    try:
        with open('CurrentCommand', 'r') as file:
            current_command = file.read()
    except FileNotFoundError:
        current_command = "No current download."

    try:
        with open('CurrentCommandLog', 'r') as file:
            current_log = file.read()
    except FileNotFoundError:
        current_log = "No logs available."

    return render_template('download_current.html', current_command=current_command, current_log=current_log)
    
    
@app.route('/Download_Queue')
def download_queue():
    command_queue = ""

    try:
        with open('CommandQueue', 'r') as file:
            command_queue = file.read()
    except FileNotFoundError:
        command_queue = "No commands in the queue."

    return render_template('download_queue.html', command_queue=command_queue)

@app.route('/Download_History')
def download_history():
    command_history = ""

    try:
        with open('CommandHistory', 'r') as file:
            command_history = file.read()
    except FileNotFoundError:
        command_history = "No history available."

    return render_template('download_history.html', command_history=command_history)

@app.route('/downloads')
def downloads():
    return render_template('downloads.html')

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        # Process form submission for sldl.conf
        sldl_settings = {
            'username': request.form.get('username'),
            'password': request.form.get('password'),
            'path': request.form.get('path'),
            'no-remove-special-chars': request.form.get('no-remove-special-chars'),
            'pref-format': request.form.get('pref-format'),
            'spotify-id': request.form.get('spotify-id'),
            'spotify-secret': request.form.get('spotify-secret'),
            'm3u': request.form.get('m3u')
        }
        write_sldl_conf(sldl_settings)

        # Process form submission for soulify.conf
        soulify_settings = {
            'UpdatemetadataWithMusicBrainz': request.form.get('UpdatemetadataWithMusicBrainz') == 'true',
            'UpdateLibraryMetadataAndRefreshJellyfin': request.form.get('UpdateLibraryMetadataAndRefreshJellyfin') == 'true'
        }
        write_soulify_conf(soulify_settings)

        # Process form submission for pdscript.conf
        pdscript_settings = {
            'destination_root': request.form.get('destination_root'),
            'new_artists_dir': request.form.get('new_artists_dir'),
            'API_BASE_URL': request.form.get('API_BASE_URL'),
            'API_AUTH_TOKEN': request.form.get('API_AUTH_TOKEN')
        }
        write_pdscript_conf(pdscript_settings)

        return redirect(url_for('settings'))

    # For GET request, display current settings
    sldl_settings = parse_sldl_conf(sldlConfigPath)
    soulify_settings = read_soulify_conf()
    pdscript_settings = read_pdscript_conf()

    return render_template('settings.html', sldl=sldl_settings, soulify=soulify_settings, pdscript=pdscript_settings)


    
if __name__ == '__main__':
    # Start the command execution loop in a separate thread
    command_thread = Thread(target=execute_command_loop)
    command_thread.daemon = True  # Ensure it exits when the main program does
    command_thread.start()

    # Run the Flask app
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
