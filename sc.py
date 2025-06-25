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
                LATEST_IMAGE_DATA = img_data
                # Store the path of the *new* file. We'll delete the *old* one next.
                old_screenshot_file = CURRENT_SCREENSHOT_FILE_ON_DISK
                CURRENT_SCREENSHOT_FILE_ON_DISK = unique_screenshot_filename
            
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

if __name__ == '__main__':
    # Initial checks for necessary tools
    try:
        subprocess.run(["which", "scrot"], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        print("ERROR: 'scrot' command not found. Please install it: sudo apt install scrot", file=sys.stderr)
        sys.exit(1)
    
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
    except Exception as e:
        print(f"[{datetime.datetime.now().isoformat()}] CRITICAL ERROR in main server loop: {e}", file=sys.stderr)
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
        if capture_thread.is_alive():
            # In case of explicit exception, ensure thread is signaled to stop
            if hasattr(capture_thread, 'running'):
                capture_thread.running = False
            capture_thread.join(timeout=1) # Give it a moment to finish

        print(f"[{datetime.datetime.now().isoformat()}] Server stopped.")
