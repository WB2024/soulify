import os
import shutil
import logging
import subprocess
import requests  # For making API calls
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
import configparser

# Setup logging
script_dir = os.path.dirname(os.path.realpath(__file__))
log_file = os.path.join(script_dir, "music_sorting.log")
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Path to the config files (2 folder levels above the script)
config_dir = os.path.abspath(os.path.join(script_dir, "../../"))
sldl_conf_path = os.path.join(config_dir, 'sldl.conf')
pdscript_conf_path = os.path.join(config_dir, 'pdscript.conf')

# Function to read configurations
def load_config():
    config_sldl = configparser.ConfigParser()
    config_sldl.read(sldl_conf_path)

    config_pdscript = configparser.ConfigParser()
    config_pdscript.read(pdscript_conf_path)

    # Extract values from sldl.conf
    source_root = config_sldl.get('General Download Settings', 'path')

    # Extract values from pdscript.conf
    destination_root = config_pdscript.get('Paths', 'destination_root')
    new_artists_dir = config_pdscript.get('Paths', 'new_artists_dir')

    API_BASE_URL = config_pdscript.get('API Details', 'API_BASE_URL')
    API_AUTH_TOKEN = config_pdscript.get('API Details', 'API_AUTH_TOKEN')

    return source_root, destination_root, new_artists_dir, API_BASE_URL, API_AUTH_TOKEN

# Load configuration variables
source_root, destination_root, new_artists_dir, API_BASE_URL, API_AUTH_TOKEN = load_config()

# API headers
HEADERS = {
    'Authorization': f'MediaBrowser Token={API_AUTH_TOKEN}',
    'accept': 'application/json',
    'Content-Type': 'application/json'
}

# Function to set permissions
def set_permissions(path):
    try:
        os.chmod(path, 0o777)
        logging.info(f"Set permissions to 777 for {path}")
    except Exception as e:
        logging.error(f"Failed to set permissions for {path}: {e}")

# Function to move files and check size
def move_and_compare(src_file, dst_file):
    src_size = os.path.getsize(src_file)
    if os.path.exists(dst_file):
        dst_size = os.path.getsize(dst_file)
        if src_size > dst_size:
            os.remove(dst_file)
            shutil.move(src_file, dst_file)
            logging.info(f"Moved larger file from {src_file} to {dst_file}")
        else:
            os.remove(src_file)
            logging.info(f"Deleted smaller file {src_file} because {dst_file} is larger")
    else:
        shutil.move(src_file, dst_file)
        logging.info(f"Moved file {src_file} to {dst_file}")

# Function to update metadata using mutagen
def update_metadata(file_path, genre, album_artist):
    try:
        if file_path.endswith('.mp3'):
            audio = EasyID3(file_path)
            audio['genre'] = genre
            audio['albumartist'] = album_artist
            audio.save()
        elif file_path.endswith('.flac'):
            audio = FLAC(file_path)
            audio['genre'] = genre
            audio['albumartist'] = album_artist
            audio.save()
        elif file_path.endswith('.m4a') or file_path.endswith('.mp4'):
            audio = MP4(file_path)
            audio['\xa9gen'] = genre
            audio['aART'] = album_artist
            audio.save()
        else:
            logging.warning(f"Unsupported file format: {file_path}")
            return False
        logging.info(f"Updated metadata for {file_path}: Genre = {genre}, Album Artist = {album_artist}")
        return True
    except Exception as e:
        logging.error(f"Error updating metadata for {file_path}: {e}")
        return False

# Function to make GET request and fetch artist details
def fetch_artist_info(artist_name):
    try:
        url = f"{API_BASE_URL}/Artists/{artist_name}"
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            artist_info = response.json()
            logging.info(f"Successfully fetched artist info for {artist_name}")
            return artist_info
        else:
            logging.error(f"Failed to fetch artist info for {artist_name}: Status {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"Error fetching artist info for {artist_name}: {e}")
        return None

# Function to refresh artist metadata using the artist ID
def refresh_artist_metadata(artist_id):
    try:
        url = f"{API_BASE_URL}/Items/{artist_id}/Refresh?Recursive=true&ImageRefreshMode=Default&MetadataRefreshMode=Default&ReplaceAllImages=false&ReplaceAllMetadata=false"
        response = requests.post(url, headers=HEADERS)
        if response.status_code == 204:
            logging.info(f"Successfully refreshed metadata for artist ID {artist_id}")
        else:
            logging.error(f"Failed to refresh metadata for artist ID {artist_id}: Status {response.status_code}")
    except Exception as e:
        logging.error(f"Error refreshing metadata for artist ID {artist_id}: {e}")

# Function to process each artist folder
def process_artist_folder(artist_folder):
    artist_name = os.path.basename(artist_folder)
    logging.info(f"Processing artist folder: {artist_name}")

    # Recursively search for the artist in the destination root
    match_found = False
    for root, dirs, files in os.walk(destination_root):
        if artist_name in dirs:
            destination_artist_folder = os.path.join(root, artist_name)
            genre_folder = os.path.basename(os.path.dirname(destination_artist_folder))
            logging.info(f"Found matching artist folder: {destination_artist_folder} with Genre: {genre_folder}")
            match_found = True

            # Move all files and subfolders from source to destination
            for src_root, _, src_files in os.walk(artist_folder):
                dst_root = src_root.replace(artist_folder, destination_artist_folder, 1)
                os.makedirs(dst_root, exist_ok=True)

                # Set permissions for the destination folder
                set_permissions(dst_root)

                for file in src_files:
                    src_file = os.path.join(src_root, file)
                    dst_file = os.path.join(dst_root, file)

                    # Move and compare files based on size
                    move_and_compare(src_file, dst_file)

                    # Update metadata for supported formats
                    update_metadata(dst_file, genre_folder, artist_name)

            # Make API calls to fetch artist info and refresh metadata
            artist_info = fetch_artist_info(artist_name)
            if artist_info and 'Id' in artist_info:
                refresh_artist_metadata(artist_info['Id'])

            break

    if not match_found:
        # No matching artist folder found, move to new artists directory
        new_artist_folder = os.path.join(new_artists_dir, artist_name)
        shutil.move(artist_folder, new_artist_folder)
        logging.info(f"Moved artist folder {artist_folder} to {new_artist_folder}")

    # Check if the source artist folder is empty and delete if necessary
    if not os.listdir(artist_folder):
        os.rmdir(artist_folder)
        logging.info(f"Deleted empty artist folder: {artist_folder}")

# Main function to iterate through all artist folders in the source root
def main():
    if not os.path.exists(new_artists_dir):
        os.makedirs(new_artists_dir)

    for item in os.listdir(source_root):
        artist_folder = os.path.join(source_root, item)
        if os.path.isdir(artist_folder):
            process_artist_folder(artist_folder)

    # Run the command to find and delete empty directories after all operations
    try:
        logging.info("Running find command to delete empty directories in sorting")
        subprocess.run(["find", source_root, "-mindepth", "1", "-type", "d", "-empty", "-delete"], check=True)
        logging.info("Successfully deleted empty directories")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running find command: {e}")

if __name__ == "__main__":
    main()
