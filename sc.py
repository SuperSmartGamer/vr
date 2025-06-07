import subprocess
import os
import time
import sys

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
            # Captures stdout and stderr, checks for non-zero exit code
            result = subprocess.run(command, capture_output=True, text=True, check=True, shell=True)
            return result.stdout.strip()
        else:
            # Runs command, prints stdout/stderr if error, checks for non-zero exit code
            result = subprocess.run(command, check=True, shell=True, capture_output=True, text=True)
            if result.stdout:
                print(f"Command STDOUT: {result.stdout.strip()}")
            if result.stderr:
                print(f"Command STDERR: {result.stderr.strip()}")
            return True
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e.cmd}")
        print(f"STDOUT: {e.stdout.strip()}")
        print(f"STDERR: {e.stderr.strip()}")
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
    print(f"Starting X11 screen sharing sender to {RECEIVER_TAILSCALE_IP}:{RECEIVER_PORT} at {FPS} FPS...")
    
    while True:
        start_time = time.time()
        
        # 1. Take screenshot with gnome-screenshot
        # -f: specify filename
        # -e: capture the entire screen
        # -j: save as JPEG
        # -q <quality>: JPEG quality (0-100)
        # Using 2>/dev/null to suppress gnome-screenshot's own stderr messages
        screenshot_command = f"gnome-screenshot -f '{FULL_PATH}' -e -j -q {JPEG_QUALITY} 2>/dev/null"
        
        print(f"Capturing screen to {FULL_PATH} with gnome-screenshot...")
        capture_success = run_command(screenshot_command)

        if capture_success and os.path.exists(FULL_PATH) and os.path.getsize(FULL_PATH) > 0:
            print("Screenshot taken successfully.")

            # 2. Send the image to the receiver using curl
            curl_command = f"curl -s -X PUT --data-binary '@{FULL_PATH}' http://{RECEIVER_TAILSCALE_IP}:{RECEIVER_PORT}/{SCREENSHOT_NAME}"
            
            print(f"Sending image to {RECEIVER_TAILSCALE_IP}:{RECEIVER_PORT}...")
            send_success = run_command(curl_command)

            if send_success:
                print("Image sent successfully.")
            else:
                print("Failed to send image via curl.")
        else:
            print("Screenshot failed or was blocked. Verify gnome-screenshot works from your terminal manually.")
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
        
        print(f"Frame processed in {elapsed_time:.2f}s. Sleeping for {max(0, sleep_time):.2f}s.")

if __name__ == "__main__":
    print("\nIMPORTANT: This script is for X11 environments. Ensure you are running it as the user logged into the graphical desktop, NOT with 'sudo'.")
    print("Run 'echo $DISPLAY' in your terminal. It should show something like ':0'.")
    print("For background operation, use 'nohup python3 sender_gnome_curl_X11.py &' after launching as user.\n")
    send_screen_data()