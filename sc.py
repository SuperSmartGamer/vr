#!/usr/bin/env python3

import threading
import time
import subprocess
import os
import sys
import datetime # For better logging timestamps
from http.server import SimpleHTTPRequestHandler, HTTPServer

# --- Configuration for Zorin OS MacBook (Server) ---
# IMPORTANT: Adjust these to match your Zorin OS MacBook's environment
DISPLAY_ID = ":1"  # Your X display ID (e.g., :0, :1)
XAUTH_PATH = "/run/user/1001/gdm/Xauthority" # Path to your Xauthority file
TARGET_USER = "angel-alikhanstudentscusdedu24" # Your username on the Zorin OS machine

WEB_SERVER_PORT = 18001 # Port for this HTTP server (e.g., 18001 to match previous setup)
SCREENSHOT_INTERVAL_SECONDS = 3.0 # Changed to 3.0 seconds for less frequent updates
TEMP_CAPTURE_DIR = "/tmp/live_screenshots_buffer" # Directory for unique temporary files

# --- Global variables for image data and thread safety ---
LATEST_IMAGE_DATA = None
IMAGE_DATA_LOCK = threading.Lock()
# Store the path of the *currently served* screenshot file on disk for cleanup
CURRENT_SCREENSHOT_FILE_ON_DISK = None 

# --- HTML Content for the simple viewer (served by this script) ---
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
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_VIEWER_CONTENT.encode('utf-8'))
        elif self.path.startswith('/latest_screenshot.png'):
            with IMAGE_DATA_LOCK:
                data = LATEST_IMAGE_DATA
            
            # Check if data exists AND is not empty before attempting to send
            if not data or not isinstance(data, bytes) or len(data) == 0:
                print(f"[{datetime.datetime.now().isoformat()}] INFO: Client requested /latest_screenshot.png, but no valid image data available yet. Sending 503.")
                return self.send_error(503, "Service Unavailable: No screenshot data yet.")
            
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            # More aggressive caching headers
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0, post-check=0, pre-check=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.send_header('X-Image-Refresh-Timestamp', str(time.time())) # New header for debugging
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

def capture_loop():
    """Continuously captures screenshots and updates the global image data."""
    global LATEST_IMAGE_DATA, CURRENT_SCREENSHOT_FILE_ON_DISK
    print(f"[{datetime.datetime.now().isoformat()}] Starting screenshot capture loop...")

    # Ensure the temporary directory exists
    os.makedirs(TEMP_CAPTURE_DIR, exist_ok=True)

    while True:
        # Generate a unique filename for the new screenshot
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        unique_screenshot_filename = os.path.join(TEMP_CAPTURE_DIR, f"capture_{timestamp}.png")

        # Build the scrot command with proper environment variables for X display access
        scrot_command = [
            "sudo", "-u", TARGET_USER,
            f"DISPLAY={DISPLAY_ID}",
            f"XAUTHORITY={XAUTH_PATH}",
            "scrot", "-z", unique_screenshot_filename # Use the unique filename
        ]

        try:
            # Print the command being executed for debugging
            print(f"[{datetime.datetime.now().isoformat()}] Executing scrot: {' '.join(scrot_command)}")
            
            # Execute scrot
            process_result = subprocess.run(
                scrot_command,
                check=False, # We'll check returncode manually for louder failure
                capture_output=True,
                text=True,
                env={"DISPLAY": DISPLAY_ID, "XAUTHORITY": XAUTH_PATH}
            )

            if process_result.returncode != 0:
                # Scrot failed: print detailed error and raise an exception to stop
                error_output = process_result.stderr.strip()
                error_message = (
                    f"ERROR: scrot command failed with exit code {process_result.returncode}.\n"
                    f"  Command: {' '.join(scrot_command)}\n"
                    f"  STDOUT: {process_result.stdout.strip()}\n"
                    f"  STDERR: {error_output}"
                )
                print(f"[{datetime.datetime.now().isoformat()}] {error_message}", file=sys.stderr)
                raise RuntimeError(f"Critical scrot error: {error_message}")

            # Read the captured image data from the unique file
            if not os.path.exists(unique_screenshot_filename):
                raise FileNotFoundError(f"Scrot command executed, but file not found: {unique_screenshot_filename}")

            with open(unique_screenshot_filename, 'rb') as f:
                img_data = f.read()
            
            # Update the global variable with the new image data and path
            with IMAGE_DATA_LOCK:
                old_screenshot_file = CURRENT_SCREENSHOT_FILE_ON_DISK # Get the path of the previous file
                LATEST_IMAGE_DATA = img_data
                CURRENT_SCREENSHOT_FILE_ON_DISK = unique_screenshot_filename # Set to the new file's path
            
            print(f"[{datetime.datetime.now().isoformat()}] Screenshot captured and loaded: {unique_screenshot_filename}")

            # Clean up the old screenshot file
            if old_screenshot_file and os.path.exists(old_screenshot_file):
                try:
                    os.remove(old_screenshot_file)
                    print(f"[{datetime.datetime.now().isoformat()}] Cleaned up old file: {old_screenshot_file}")
                except OSError as e:
                    print(f"[{datetime.datetime.now().isoformat()}] Warning: Could not delete old screenshot file {old_screenshot_file}: {e}", file=sys.stderr)

        except FileNotFoundError as e:
            print(f"[{datetime.datetime.now().isoformat()}] FATAL ERROR: {e}. Please ensure scrot is installed and configured.", file=sys.stderr)
            raise # Re-raise to ensure main thread catches and exits loudly
        except Exception as e:
            print(f"[{datetime.datetime.now().isoformat()}] UNEXPECTED ERROR in capture loop: {e}", file=sys.stderr)
            raise # Re-raise to ensure main thread catches and exits loudly

        time.sleep(SCREENSHOT_INTERVAL_SECONDS)

def kill_process_on_port(port):
    """
    Attempts to find and kill any process listening on the specified TCP port.
    Requires 'lsof' and 'kill' commands to be available and root privileges for lsof.
    """
    print(f"[{datetime.datetime.now().isoformat()}] Attempting to kill any existing process on port {port}...")
    try:
        # Find PID using lsof. -t for PIDs only, -i :port for network files by port.
        # This needs sudo because other processes might be owned by other users.
        lsof_command = ["sudo", "lsof", "-ti", f"tcp:{port}"]
        result = subprocess.run(lsof_command, capture_output=True, text=True, check=False)

        if result.returncode == 0 and result.stdout:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid.strip().isdigit():
                    pid = pid.strip()
                    print(f"[{datetime.datetime.now().isoformat()}] Found process {pid} on port {port}. Attempting to kill...")
                    try:
                        # Use sudo to kill the process, as it might not be owned by the current user
                        subprocess.run(["sudo", "kill", "-9", pid], check=True, capture_output=True, text=True)
                        print(f"[{datetime.datetime.now().isoformat()}] Successfully killed process {pid}.")
                    except subprocess.CalledProcessError as e:
                        print(f"[{datetime.datetime.now().isoformat()}] ERROR: Failed to kill process {pid}: {e.stderr.strip()}", file=sys.stderr)
                    except Exception as e:
                        print(f"[{datetime.datetime.now().isoformat()}] UNEXPECTED ERROR while killing process {pid}: {e}", file=sys.stderr)
                else:
                    print(f"[{datetime.datetime.now().isoformat()}] WARNING: Non-numeric PID found in lsof output: '{pid}'", file=sys.stderr)
        else:
            print(f"[{datetime.datetime.now().isoformat()}] No process found on port {port}.")
    except FileNotFoundError:
        print(f"[{datetime.datetime.now().isoformat()}] ERROR: 'lsof' or 'kill' command not found. Cannot force-kill processes on port.", file=sys.stderr)
        print("Please install 'lsof' (e.g., sudo apt install lsof) if you need this functionality.", file=sys.stderr)
    except Exception as e:
        print(f"[{datetime.datetime.now().isoformat()}] UNEXPECTED ERROR while checking/killing port {port}: {e}", file=sys.stderr)


if __name__ == '__main__':
    # Initial checks for necessary tools
    try:
        subprocess.run(["which", "scrot"], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        print("ERROR: 'scrot' command not found. Please install it: sudo apt install scrot", file=sys.stderr)
        sys.exit(1)
    
    # Check for lsof and install recommendation if not found
    try:
        subprocess.run(["which", "lsof"], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        print("WARNING: 'lsof' command not found. The script might not be able to force-kill processes on port.", file=sys.stderr)
        print("Consider installing 'lsof': sudo apt install lsof", file=sys.stderr)

    # Force-kill any existing processes on the target port before starting the server
    kill_process_on_port(WEB_SERVER_PORT)

    # Start the screenshot capture loop in a separate daemon thread
    capture_thread = threading.Thread(target=capture_loop, daemon=True)
    
    try:
        capture_thread.start() # Start the capture thread
        # Give capture thread a moment to generate the first screenshot
        time.sleep(1) 

        # Start the HTTP server in the main thread
        print(f"[{datetime.datetime.now().isoformat()}] Serving HTTP on port {WEB_SERVER_PORT}, access via Tailscale IP.")
        print(f"To stop, press Ctrl-C.")
        HTTPServer(('', WEB_SERVER_PORT), CustomHTTPHandler).serve_forever()

    except KeyboardInterrupt:
        print(f"[{datetime.datetime.now().isoformat()}] Server shutting down...")
    except OSError as e: # Catch specific OSError for 'Address already in use' directly here
        if e.errno == 98:
            print(f"[{datetime.datetime.now().isoformat()}] CRITICAL ERROR: Port {WEB_SERVER_PORT} is still in use after attempted cleanup. Please manually verify and kill the process, then restart.", file=sys.stderr)
        else:
            print(f"[{datetime.datetime.now().isoformat()}] CRITICAL OS ERROR: {e}", file=sys.stderr)
        sys.exit(1) # Exit if port is still in use
    except Exception as e:
        print(f"[{datetime.datetime.now().isoformat()}] CRITICAL UNEXPECTED ERROR in main server loop: {e}", file=sys.stderr)
        sys.exit(1) # Exit on other critical errors
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
        
        # Ensure daemon threads have a chance to terminate cleanly (though daemon threads exit when main exits)
        if threading.main_thread().is_alive(): # Check if main thread is still running before joining daemons
            if capture_thread.is_alive():
                # In case of explicit exception, ensure thread is signaled to stop
                # Note: Daemon threads will exit with the main thread, this is mostly for explicit signaling
                pass # The exception will cause main thread to exit, taking daemons with it.

        print(f"[{datetime.datetime.now().isoformat()}] Server stopped.")
