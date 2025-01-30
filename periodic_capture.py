"""
PERIODIC CAPTURE - Automated Image Capture for GoPro

This script captures images on a GoPro at a regular interval, downloads them, 
and saves them to a local folder. After downloading, it deletes the images 
from the GoPro SD card to free up space. The script also sends periodic 
keep-alive requests to maintain the connection as per GoPro's specifications.

Usage:
    python periodic_capture.py --ip 172.2X.1YZ.51 --port 8080

Where:
    - `XYZ` corresponds to the last three digits of the GoPro serial number.

Author: Vincent Free
Date: 2025-01-31
"""

import requests
import threading
import time
import argparse
import os
import json

VERBOSE_HTTP_REQUESTS = False
DELETE_FROM_SD = True
KEEP_ALIVE_INTERVAL_SEC = 3

class OpenGoProClient:
    def __init__(self, ip, port, preset):
        self.base_url = f"http://{ip}:{port}"
        self.media_url = f"http://{ip}:8080/videos/DCIM"
        self.camera_preset_id = preset
        self.keep_alive_interval = KEEP_ALIVE_INTERVAL_SEC
        self.photo_interval = 0
        self.latest_media = None
        self.running = True
        self.lock = threading.Lock()  # Lock to prevent overlapping requests

    def get(self, url: str, stream: bool = False, retries=3, delay=1):
        """Thread-safe HTTP GET request with retries and proper lock handling."""
        attempt = 0
        while attempt < retries:
            try:
                if VERBOSE_HTTP_REQUESTS:
                    print(f"[HTTP Request] Sending GET request to: {url}")

                with self.lock:  # Ensure only one request executes at a time
                    response = requests.get(url, stream=stream, timeout=5)  # Add timeout

                if response.status_code == 200:
                    return response  # Success, return response
                else:
                    print(f"[HTTP Error] Status: {response.status_code} - Attempt {attempt + 1}")

            except requests.RequestException as e:
                print(f"[HTTP Error] Attempt {attempt + 1} failed: {e}")

            attempt += 1
            time.sleep(delay)  # Exponential backoff could be implemented here

        return None  # Return None after all retries fail

    def send_keep_alive(self):
        """Sends periodic keep-alive messages to the GoPro."""
        while self.running:
            try:
                response = self.get(f"{self.base_url}/gopro/camera/keep_alive")
                if response.status_code == 200:
                    print("[Keep-Alive] Sent successfully.")
                else:
                    print(f"[Keep-Alive] Error: {response.status_code}")
            except Exception as e:
                print(f"[Keep-Alive] Failed: {e}")
            time.sleep(self.keep_alive_interval)

    def take_photo_and_download(self):
        """Continuously captures and downloads images with minimal delay."""
        
        last_photo_time = time.monotonic() - self.photo_interval  # Ensures an immediate trigger
        media_list = self.get_media_list()  # Get initial media list once

        while self.running:
            now = time.monotonic()

            # Check if it's time to take a new photo
            if now - last_photo_time >= self.photo_interval:
                last_photo_time = now  # Update last photo time

                try:
                    # Trigger photo capture
                    capture_response = self.get(f"{self.base_url}/gopro/camera/shutter/start")
                    if capture_response and capture_response.status_code == 200:
                        print("[Photo] Capture triggered.")
                    else:
                        print(f"[Photo] Capture failed: {capture_response.status_code if capture_response else 'No response'}")
                        continue  # Skip to next loop iteration

                    # Wait for the camera to process the photo (smarter polling)
                    start_wait = time.monotonic()
                    max_wait_time = 7  # Reduce max wait time for new media
                    wait_time = 0.1  # Start with a short wait time
                    new_media_list = None

                    while time.monotonic() - start_wait < max_wait_time:
                        after_files_response = self.get(f"{self.base_url}/gopro/media/list")
                        if after_files_response and after_files_response.status_code == 200:
                            new_media_list = self.get_media_list()
                            if new_media_list and len(new_media_list) > len(media_list):
                                break  # Found new media, stop polling
                        elif after_files_response and after_files_response.status_code == 503:
                            print("[Photo] Camera is busy, retrying...")
                        
                        time.sleep(wait_time)
                        wait_time = min(wait_time * 2, 1.0)  # Exponential backoff, max 1s

                    if not new_media_list:
                        print("[Photo] Failed to retrieve new media list.")
                        continue

                    # Identify the new file
                    new_files = list(set(new_media_list) - set(media_list))
                    if new_files:
                        latest_photo = sorted(new_files)[-1]
                        print(f"[Photo] New image detected: {latest_photo}")

                        # Start download in a separate thread to allow next capture faster
                        # download_thread = threading.Thread(target=self.download_and_delete, args=(latest_photo,))
                        # download_thread.start()
                        self.download_and_delete(latest_photo)

                        # Update media list for the next iteration
                        media_list = new_media_list
                    else:
                        print("[Photo] No new image detected.")

                except Exception as e:
                    print(f"[Photo] Error: {e}")

            time.sleep(0.02)  # Reduce CPU usage while still allowing fast response

    def get_media_list(self):
        """Retrieves a list of media files on the GoPro."""
        try:
            response = self.get(f"{self.base_url}/gopro/media/list")
            if response.status_code == 200:
                media_list = response.json()
                if "media" in media_list and len(media_list["media"]) > 0:
                    folder = media_list["media"][0]["d"]
                    files = [f"{folder}/{item['n']}" for item in media_list["media"][0]["fs"]]
                    return files
            print("[Media] No media found.")
        except Exception as e:
            print(f"[Media] Error fetching media list: {e}")
        return []
    
    def download_and_delete(self, filename):
        """Downloads and optionally deletes the photo."""
        self.download_photo(filename)
        if DELETE_FROM_SD:
            self.delete_file(filename)

    def download_photo(self, filename):
        """Downloads the latest photo from the GoPro."""
        try:
            # Extract only the filename, removing any folder structure
            filename_only = os.path.basename(filename)  # Extracts "GOPR0188.JPG"
            local_filename = os.path.join("photos", filename_only)

            # Ensure the "photos" directory exists
            os.makedirs("photos", exist_ok=True)

            # Correctly format the URL
            url = f"http://{self.base_url.split('//')[1].split(':')[0]}:8080/videos/DCIM/{filename}"

            response = self.get(url, stream=True)
            if response and response.status_code == 200:
                with open(local_filename, "wb") as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                print(f"[Download] Saved: {local_filename}")
            else:
                print(f"[Download] Failed with status {response.status_code}: {url}")

        except Exception as e:
            print(f"[Download] Error: {e}")

    def delete_file(self, file: str):

        url = f"{self.base_url}/gopro/media/delete/file?path={file}"
        response = self.get(url)
        if response and response.status_code == 200:
            print(f"[Photo] Deleted file: {file}.")
        else:
            print(f"[Photo] Failed to delete file: {file}.")

    def start(self):
        """Starts the keep-alive and photo threads."""

        # Put camera into usb mode (no control) so camera is in known state.
        # response can be ignored as we don't care if it fails - this means
        # (most likely) it was already in that state.
        url = f"{self.base_url}/gopro/camera/control/wired_usb?p=0"
        response = self.get(url)

        # Check Open GoPro version
        url = f"{self.base_url}/gopro/version"
        response = self.get(url)
        if response and response.status_code == 200:
            try:
                version_info = response.json()  # Parse JSON response
                if "version" in version_info:
                    print(f"[Control] Open GoPro Version: {version_info['version']}")
                else:
                    print("[Control] Version key not found in response.")
            except json.JSONDecodeError:
                print("[Control] Response is not valid JSON.")
        else:
            print("[Control] Couldn't fetch Open GoPro version.")

        # Activate USB control mode
        url = f"{self.base_url}/gopro/camera/control/wired_usb?p=1"
        response = self.get(url)
        if response.status_code == 200:
            print("[Control] USB control activated.")
        else:
            print("[Control] USB control activation failed.")
        
        # Activate external camera control (for shutter)
        url = f"{self.base_url}/gopro/camera/control/set_ui_controller?p=2"
        response = self.get(url)
        if response.status_code == 200:
            print("[Control] External UI control activated.")
        else:
            print("[Control] Activating external UI control failed.")

        # Get camera state (status)
        url = f"{self.base_url}/gopro/camera/state"
        response = self.get(url)
        if response and response.status_code == 200:
            try:
                state_info = response.json()
                print(f"[Control] Camera State:\n{json.dumps(state_info, indent=4)}")
            except json.JSONDecodeError:
                print("[Control] Response is not valid JSON.")
        else:
            print("[Control] Failed to get camera state.")

        # Get camera presets
        url = f"{self.base_url}/gopro/camera/presets/get"
        response = self.get(url)
        if response and response.status_code == 200:
            try:
                presets_info = response.json()
                print(f"[Control] Camera Presets:\n{json.dumps(presets_info, indent=4)}")
            except json.JSONDecodeError:
                print("[Control] Response is not valid JSON.")
        else:
            print("[Control] Failed to get camera presets.")

        # Set camera preset
        url = f"{self.base_url}/gopro/camera/presets/load?id={self.camera_preset_id}"
        response = self.get(url)
        if response.status_code == 200:
            print(f"[Control] Set camera preset ID: {self.camera_preset_id}")
        else:
            print("[Control] Failed to set camera preset.")

        keep_alive_thread = threading.Thread(target=self.send_keep_alive, daemon=True)
        photo_thread = threading.Thread(target=self.take_photo_and_download, daemon=True)

        keep_alive_thread.start()
        photo_thread.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[Shutdown] Stopping threads.")
            self.running = False
            keep_alive_thread.join()
            photo_thread.join()
            print("[Shutdown] All threads stopped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Open GoPro API Client")
    parser.add_argument("--ip", required=True, help="GoPro Camera IP Address")
    parser.add_argument("--port", default="8080", help="GoPro API Port (default: 8080)")
    parser.add_argument("--preset", default="65536", help="GoPro Preset ID (default: 65536)")
    args = parser.parse_args()

    client = OpenGoProClient(args.ip, args.port, args.preset)
    client.start()
