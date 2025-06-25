#!/usr/bin/env python3

import threading
import time
import subprocess
import os
import sys
import datetime # For better logging timestamps
from http.server import SimpleHTTPRequestHandler, HTTPServer
import socket # For checking port availability

# --- Configuration for Zorin OS MacBook (Server) ---
# IMPORTANT: Adjust these to match your Zorin OS MacBook's environment
DISPLAY_ID = ":1"  # Your X display ID (e.g., :0, :1)
XAUTH_PATH = "/run/user/1001/gdm/Xauthority" # Path to your Xauthority file
TARGET_USER = "angel-alikhanstudentscusdedu24" # Your username on the Zorin OS machine

INITIAL_WEB_SERVER_PORT = 18001 # Starting port for the HTTP server
MAX_PORT_ATTEMPTS = 10 # How many ports to try (e.g., 18001, 18002, ..., 18010)
SCREENSHOT_INTERVAL_SECONDS = 3.0 # Screenshot update interval
TEMP_CAPTURE_DIR = "/tmp/live_screenshots_buffer" # Directory for unique temporary files

# --- Global variables for image data and thread safety ---
LATEST_IMAGE_DATA = None
IMAGE_DATA_LOCK = threading.Lock()
CURRENT_SCREENSHOT_FILE_ON_DISK = None 

# --- Client Activity Management ---
# Event to signal the capture thread to start/stop
_capture_active_event = threading.Event()
# Timestamp of the last client request for /latest_screenshot.png
last_client_request_time = 0
# Seconds after which capture stops if no client requests are received
CLIENT_INACTIVITY_TIMEOUT_SECONDS = 15 


# --- HTML Content for the simple viewer (served by this script) ---
# Note: The JS refresh interval should ideally match SCREENSHOT_INTERVAL_SECONDS
HTML_VIEWER_CONTENT = f"""\
<!DOCTYPE html>
<html>
<head>
    <title>Zorin OS Live Feed</title>
    <style>
        body {{ margin: 0; overflow: hidden; background-color: #333; }}
        img {{
            width: 100vw;
            height: 100vh;
            object-fit: contain; /* Ensures the image fits without cropping */
            display: block; /* Remove extra space below image */
        }}
    </style>
</head>
<body>
    <div id="image-container" style="width:100vw;height:100vh;">
        <img id="live-feed-shot" src="/latest_screenshot.png" alt="Live Screenshot">
    </div>
    <script>
        setInterval(() => {{
            const container = document.getElementById('image-container');
            const oldImg = document.getElementById('live-feed-shot');

            // Create a new image element
            const newImg = new Image();
            newImg.id = 'live-feed-shot';
            newImg.alt = 'Live Screenshot';
            newImg.style.width = '100vw'; // Maintain styling
            newImg.style.height = '100vh';
            newImg.style.objectFit = 'contain';
            newImg.style.display = 'block';

            // Set the new source with cache-busting timestamp
            newImg.src = '/latest_screenshot.png?_=' + Date.now();

            // Replace the old image with the new one
            if (oldImg) {{
                container.replaceChild(newImg, oldImg);
            }} else {{
                // In case the oldImg doesn't exist for some reason on first load
                container.appendChild(newImg);
            }}
        }}, {int(SCREENSHOT_INTERVAL_SECONDS * 1000)}); // Refresh rate in milliseconds
    </script>
</body>
</html>
"""

class CustomHTTPHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler to serve the live screenshot and HTML viewer."""
    def do_GET(self):
        global last_client_request_time
        
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_VIEWER_CONTENT.encode('utf-8'))
        elif self.path.startswith('/latest_screenshot.png'):
            # A client is requesting the stream, so mark activity and activate capture
            last_client_request_time = time.time()
            if not _capture_active_event.is_set():
                print(f"[{datetime.datetime.now().isoformat()}] Client activity detected. Activating screenshot capture.")
                _capture_active_event.set() # Signal capture loop to run

            with IMAGE_DATA_LOCK:
                data = LATEST_IMAGE_DATA
            
            if not data or not isinstance(data, bytes) or len(data) == 0:
                print(f"[{datetime.datetime.now().isoformat()}] INFO: Client requested /latest_screenshot.png, but no valid image data available yet. Sending 503.")
                return self.send_error(503, "Service Unavailable: No screenshot data yet.")
            
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0, post-check=0, pre-check=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.send_header('X-Image-Refresh-Timestamp', str(time.time()))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

def capture_loop():
    """Continuously captures screenshots and updates the global image data."""
    global LATEST_IMAGE_DATA, CURRENT_SCREENSHOT_FILE_ON_DISK
    print(f"[{datetime.datetime.now().isoformat()}] Screenshot capture loop initialized (waiting for client activity).")

    while True:
        # Wait until _capture_active_event is set (signaled by client activity)
        # Timeout is for responsiveness if the event is cleared
        _capture_active_event.wait(timeout=1) # Wait with a small timeout to allow checking `is_set()` quickly

        # Only run capture if the event is set
        if _capture_active_event.is_set():
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
            unique_screenshot_filename = os.path.join(TEMP_CAPTURE_DIR, f"capture_{timestamp}.png")

            scrot_command = [
                "sudo", "-u", TARGET_USER,
                f"DISPLAY={DISPLAY_ID}",
                f"XAUTHORITY={XAUTH_PATH}",
                "scrot", "-z", unique_screenshot_filename
            ]

            try:
                # print(f"[{datetime.datetime.now().isoformat()}] Executing scrot: {' '.join(scrot_command)}") # Too verbose when active
                
                process_result = subprocess.run(
                    scrot_command,
                    check=False,
                    capture_output=True,
                    text=True,
                    env={"DISPLAY": DISPLAY_ID, "XAUTHORITY": XAUTH_PATH}
                )

                if process_result.returncode != 0:
                    error_output = process_result.stderr.strip()
                    error_message = (
                        f"ERROR: scrot command failed with exit code {process_result.returncode}.\n"
                        f"  Command: {' '.join(scrot_command)}\n"
                        f"  STDOUT: {process_result.stdout.strip()}\n"
                        f"  STDERR: {error_output}"
                    )
                    print(f"[{datetime.datetime.now().isoformat()}] {error_message}", file=sys.stderr)
                    # On error, clear event to pause and avoid continuous error logging
                    _capture_active_event.clear()
                    print(f"[{datetime.datetime.now().isoformat()}] Capture paused due to scrot error.")
                    time.sleep(5) # Wait before attempting again if error occurred
                    continue # Go to next loop iteration to re-wait for event
                
                if not os.path.exists(unique_screenshot_filename):
                    print(f"[{datetime.datetime.now().isoformat()}] WARNING: Scrot command executed, but file not found: {unique_screenshot_filename}. Pausing capture.", file=sys.stderr)
                    _capture_active_event.clear() # Clear event to pause
                    time.sleep(5)
                    continue # Go to next loop iteration to re-wait for event

                with open(unique_screenshot_filename, 'rb') as f:
                    img_data = f.read()
                
                with IMAGE_DATA_LOCK:
                    old_screenshot_file = CURRENT_SCREENSHOT_FILE_ON_DISK
                    LATEST_IMAGE_DATA = img_data
                    CURRENT_SCREENSHOT_FILE_ON_DISK = unique_screenshot_filename
                
                # print(f"[{datetime.datetime.now().isoformat()}] Screenshot captured and loaded.") # Too verbose when active

                if old_screenshot_file and os.path.exists(old_screenshot_file):
                    try:
                        os.remove(old_screenshot_file)
                        # print(f"[{datetime.datetime.now().isoformat()}] Cleaned up old file: {old_screenshot_file}") # Too verbose
                    except OSError as e:
                        print(f"[{datetime.datetime.now().isoformat()}] Warning: Could not delete old screenshot file {old_screenshot_file}: {e}", file=sys.stderr)

            except Exception as e:
                print(f"[{datetime.datetime.now().isoformat()}] UNEXPECTED ERROR in capture loop: {e}", file=sys.stderr)
                _capture_active_event.clear() # Clear event to pause on unexpected errors
                print(f"[{datetime.datetime.now().isoformat()}] Capture paused due to unexpected error.")
                time.sleep(5) # Wait before attempting again
                continue # Go to next loop iteration to re-wait for event

            time.sleep(SCREENSHOT_INTERVAL_SECONDS)
        else:
            # If event is not set, means no client activity, so just sleep and check again
            time.sleep(1) 


def monitor_client_activity_loop():
    """Monitors client request timestamps and deactivates capture if inactive."""
    global last_client_request_time
    print(f"[{datetime.datetime.now().isoformat()}] Starting client activity monitor.")
    while True:
        if _capture_active_event.is_set():
            if (time.time() - last_client_request_time) > CLIENT_INACTIVITY_TIMEOUT_SECONDS:
                print(f"[{datetime.datetime.now().isoformat()}] No client activity for {CLIENT_INACTIVITY_TIMEOUT_SECONDS} seconds. Deactivating screenshot capture.")
                _capture_active_event.clear() # Deactivate capture
                # Optionally clear LATEST_IMAGE_DATA to free memory, but might cause 503 on re-connection
                # with IMAGE_DATA_LOCK:
                #     LATEST_IMAGE_DATA = None
        time.sleep(CLIENT_INACTIVITY_TIMEOUT_SECONDS / 2) # Check every half timeout interval


def find_available_port(start_port, max_attempts):
    """Finds an available port starting from start_port."""
    for i in range(max_attempts):
        port = start_port + i
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                s.listen(1) # Try to listen, indicates port is truly free
                print(f"[{datetime.datetime.now().isoformat()}] Port {port} is available.")
                return port
            except OSError as e:
                if e.errno == 98: # Address already in use
                    print(f"[{datetime.datetime.now().isoformat()}] Port {port} is in use, trying next...", file=sys.stderr)
                else:
                    print(f"[{datetime.datetime.now().isoformat()}] ERROR checking port {port}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"[{datetime.datetime.now().isoformat()}] UNEXPECTED ERROR during port check for {port}: {e}", file=sys.stderr)
    return None

if __name__ == '__main__':
    try:
        subprocess.run(["which", "scrot"], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        print("ERROR: 'scrot' command not found. Please install it: sudo apt install scrot", file=sys.stderr)
        sys.exit(1)
    
    # --- IMPORTANT: Ensure temporary directory is writable by TARGET_USER ---
    # This block requires sudo privileges to run correctly.
    # It sets up permissions for the TARGET_USER to write screenshots.
    print(f"[{datetime.datetime.now().isoformat()}] Setting up temporary directory permissions...")
    try:
        # Create directory using sudo -u TARGET_USER
        subprocess.run(
            ["sudo", "-u", TARGET_USER, "mkdir", "-p", TEMP_CAPTURE_DIR],
            check=True, capture_output=True, text=True
        )
        # Ensure TARGET_USER has full permissions on it, even if created by current user
        subprocess.run(
            ["sudo", "chown", TARGET_USER + ":" + TARGET_USER, TEMP_CAPTURE_DIR],
            check=True, capture_output=True, text=True
        )
        subprocess.run(
            ["sudo", "chmod", "755", TEMP_CAPTURE_DIR], # rwx for owner, rx for group/others
            check=True, capture_output=True, text=True
        )
        print(f"[{datetime.datetime.now().isoformat()}] Ensured directory {TEMP_CAPTURE_DIR} exists and is writable by {TARGET_USER}.")
    except subprocess.CalledProcessError as e:
        print(f"[{datetime.datetime.now().isoformat()}] ERROR: Could not set up temporary directory permissions: {e.stderr.strip()}", file=sys.stderr)
        print("Please ensure your user can run 'sudo mkdir', 'sudo chown', and 'sudo chmod' without a password.", file=sys.stderr)
        print("Alternatively, run this script with 'sudo python3 YOUR_SCRIPT_NAME.py'.", file=sys.stderr)
        sys.exit(1) # Exit immediately if directory setup fails
    except Exception as e:
        print(f"[{datetime.datetime.now().isoformat()}] UNEXPECTED ERROR during temporary directory setup: {e}", file=sys.stderr)
        sys.exit(1) # Exit on unexpected errors during setup
    # --- END IMPORTANT ---

    # Find an available port
    chosen_port = find_available_port(INITIAL_WEB_SERVER_PORT, MAX_PORT_ATTEMPTS)
    if chosen_port is None:
        print(f"[{datetime.datetime.now().isoformat()}] CRITICAL ERROR: Could not find an available port after {MAX_PORT_ATTEMPTS} attempts starting from {INITIAL_WEB_SERVER_PORT}.", file=sys.stderr)
        sys.exit(1)

    # Start the screenshot capture loop in a separate daemon thread
    capture_thread = threading.Thread(target=capture_loop, daemon=True)
    capture_thread.start()
    
    # Start the client activity monitoring thread
    monitor_thread = threading.Thread(target=monitor_client_activity_loop, daemon=True)
    monitor_thread.start()

    try:
        # Give capture thread a moment to initialize its internal state (not wait for event yet)
        time.sleep(1) 

        # Start the HTTP server on the chosen port
        print(f"[{datetime.datetime.now().isoformat()}] Serving HTTP on port {chosen_port}.")
        print(f"*** Access the stream in your browser or client at: http://YOUR_MACBOOK_TAILSCALE_IP:{chosen_port}/ ***")
        print(f"    (e.g., http://100.71.39.117:{chosen_port}/)")
        print(f"To stop, press Ctrl-C.")
        HTTPServer(('', chosen_port), CustomHTTPHandler).serve_forever()

    except KeyboardInterrupt:
        print(f"[{datetime.datetime.now().isoformat()}] Server shutting down...")
    except Exception as e:
        print(f"[{datetime.datetime.now().isoformat()}] CRITICAL UNEXPECTED ERROR in main server loop: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # Attempt to clean up the *last* screenshot file on exit
        if CURRENT_SCREENSHOT_FILE_ON_DISK and os.path.exists(CURRENT_SCREENSHOT_FILE_ON_DISK):
            try:
                os.remove(CURRENT_SCREENSHOT_FILE_ON_DISK)
                print(f"[{datetime.datetime.now().isoformat()}] Cleaned up final temporary file: {CURRENT_SCREENSHOT_FILE_ON_DISK}")
            except OSError as e:
                print(f"[{datetime.datetime.now().isoformat()}] Warning: Could not delete final temporary file {CURRENT_SCREENSHOT_FILE_ON_DISK}: {e}", file=sys.stderr)
        
        # Clean up the temporary directory itself if it's empty
        if os.path.exists(TEMP_CAPTURE_DIR) and not os.listdir(TEMP_CAPTURE_DIR):
            try:
                os.rmdir(TEMP_CAPTURE_DIR)
                print(f"[{datetime.datetime.now().isoformat()}] Cleaned up empty temporary directory: {TEMP_CAPTURE_DIR}")
            except OSError as e:
                print(f"[{datetime.datetime.now().isoformat()}] Warning: Could not delete empty temporary directory {TEMP_CAPTURE_DIR}: {e}", file=sys.stderr)
        
        print(f"[{datetime.datetime.now().isoformat()}] Server stopped.")
