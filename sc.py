import subprocess
import os
import time
import sys # For checking python version and providing more specific instructions

# --- Configuration ---
RECEIVER_TAILSCALE_IP = '100.81.157.107' # Your PC's Tailscale IP
RECEIVER_PORT = 8000 # This must match the port the receiver's HTTP server is listening on
FPS = 1 # Frames per second (1 or 2)
JPEG_QUALITY = 50 # JPEG quality (0-100), passed to gnome-screenshot

CAPTURE_DIR = "/tmp" # Temporary directory for screenshots
SCREENSHOT_NAME = "remote_screen.jpeg"
FULL_PATH = os.path.join(CAPTURE_DIR, SCREENSHOT_NAME)

# Calculate delay in seconds for desired FPS
DELAY = 1 / FPS

def run_command(command, check_output=False):
    """
    Helper function to run shell commands.
    """
    try:
        if check_output:
            result = subprocess.run(command, capture_output=True, text=True, check=True, shell=True)
            return result.stdout.strip()
        else:
            subprocess.run(command, check=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e.cmd}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"Error: Command not found. Make sure '{command.split(' ')[0]}' is installed and in PATH.")
        return False

def check_dependencies():
    """
    Checks if gnome-screenshot and curl are available.
    """
    print("Checking dependencies...")
    if not run_command("which gnome-screenshot"):
        print("Error: 'gnome-screenshot' not found. Please install GNOME Screenshot (e.g., 'sudo apt install gnome-screenshot').")
        sys.exit(1)
    if not run_command("which curl"):
        print("Error: 'curl' not found. Please install curl (e.g., 'sudo apt install curl').")
        sys.exit(1)
    print("Dependencies checked successfully.")


def send_screen_data():
    """
    Continuously captures, sends, and deletes screenshots.
    """
    check_dependencies()
    print(f"Starting screen sharing sender to {RECEIVER_TAILSCALE_IP}:{RECEIVER_PORT} at {FPS} FPS...")
    
    while True:
        start_time = time.time()
        
        # 1. Take screenshot
        # -f: specify filename
        # -e: capture the entire screen
        # -j: save as JPEG
        # -q <quality>: JPEG quality (0-100)
        # 2>/dev/null: Redirect stderr to null to suppress warnings from gnome-screenshot itself
        screenshot_command = f"gnome-screenshot -f '{FULL_PATH}' -e -j -q {JPEG_QUALITY} 2>/dev/null"
        
        print(f"Capturing screen to {FULL_PATH}...")
        capture_success = run_command(screenshot_command)

        if capture_success and os.path.exists(FULL_PATH) and os.path.getsize(FULL_PATH) > 0:
            print("Screenshot taken successfully.")

            # 2. Send the image to the receiver using curl
            # -s: Silent mode (don't show progress meter)
            # -X PUT: Use HTTP PUT method
            # --data-binary @<file>: Send the file as binary data
            curl_command = f"curl -s -X PUT --data-binary '@{FULL_PATH}' http://{RECEIVER_TAILSCALE_IP}:{RECEIVER_PORT}/{SCREENSHOT_NAME}"
            
            print(f"Sending image to {RECEIVER_TAILSCALE_IP}:{RECEIVER_PORT}...")
            send_success = run_command(curl_command)

            if send_success:
                print("Image sent successfully.")
            else:
                print("Failed to send image via curl.")
        else:
            print("Screenshot failed or was blocked. Likely locked screen, Wayland restrictions, or no active session.")
            # If screenshot fails, we still want to wait to avoid hammering the system
        
        # 3. Delete the temporary screenshot file
        if os.path.exists(FULL_PATH):
            try:
                os.remove(FULL_PATH)
                print(f"Deleted temporary file: {FULL_PATH}")
            except OSError as e:
                print(f"Error deleting file {FULL_PATH}: {e}")

        # Control frame rate
        end_time = time.time()
        elapsed_time = end_time - start_time
        sleep_time = DELAY - elapsed_time

        if sleep_time > 0:
            time.sleep(sleep_time)
        
        # If FPS is very low and elapsed_time is longer than DELAY, don't sleep
        print(f"Frame processed in {elapsed_time:.2f}s. Sleeping for {max(0, sleep_time):.2f}s.")

if __name__ == "__main__":
    # Ensure this script is run as the user logged into the graphical session, not with sudo.
    # gnome-screenshot (and other graphical tools) requires access to the user's display session.
    print("\nIMPORTANT: Ensure this script is run as the user logged into the graphical desktop, NOT with 'sudo'.")
    print("For background operation, use 'nohup python3 sender_gnome_curl.py &' after launching as user.\n")
    send_screen_data()