import subprocess
import os
import time
import sys

# --- Configuration ---
RECEIVER_TAILSCALE_IP = '100.96.244.18' # Your PC's Tailscale IP (from your Tailscale console)
RECEIVER_PORT = 8000 # Must match the port the receiver's HTTP server is listening on
FPS = 1 # Frames per second (e.g., 1 for 1 FPS, 2 for 2 FPS)
JPEG_QUALITY = 60 # JPEG quality (0-100). 60-75 is a good balance for compression/quality.

CAPTURE_DIR = "/tmp" # Temporary directory for screenshots
SCREENSHOT_NAME = "remote_screen.jpeg" # Filename for the screenshot
FULL_PATH = os.path.join(CAPTURE_DIR, SCREENSHOT_NAME)

# Calculate delay in seconds for desired FPS
DELAY_SECONDS = 1 / FPS

def run_command(command_args, check_output=False, suppress_stderr=True):
    """
    Helper function to run shell commands using subprocess.run().
    command_args: List of command and its arguments.
    check_output: If True, returns stdout and raises error on non-zero exit.
    suppress_stderr: If True, redirects stderr to /dev/null for stealth.
    """
    stderr_target = subprocess.DEVNULL if suppress_stderr else None
    
    # Crucial: Explicitly copy the current environment for the subprocess
    # This ensures DISPLAY and other necessary XDG variables are passed.
    current_env = os.environ.copy()

    try:
        if check_output:
            result = subprocess.run(command_args, capture_output=True, text=True, check=True, stderr=stderr_target, env=current_env)
            return result.stdout.strip()
        else:
            result = subprocess.run(command_args, check=True, stderr=stderr_target, capture_output=True, text=True, env=current_env)
            if result.stdout:
                print(f"Command STDOUT: {result.stdout.strip()}")
            if result.stderr and not suppress_stderr: # Only print if not suppressed
                print(f"Command STDERR: {result.stderr.strip()}")
            return True
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {' '.join(e.cmd)}")
        print(f"STDOUT: {e.stdout.strip()}")
        print(f"STDERR: {e.stderr.strip()}")
        return False
    except FileNotFoundError:
        print(f"Error: Command not found. Make sure '{command_args[0]}' is installed and in PATH.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred while running command: {e}")
        return False

def check_dependencies():
    """
    Checks if gnome-screenshot and curl are available.
    """
    print("Checking dependencies...")
    if not run_command(["which", "gnome-screenshot"], check_output=True):
        print("Error: 'gnome-screenshot' not found. Please install GNOME Screenshot (e.g., 'sudo apt install gnome-screenshot').")
        sys.exit(1)
    if not run_command(["which", "curl"], check_output=True):
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
        
        # 1. Take screenshot with gnome-screenshot
        screenshot_command_args = [
            "gnome-screenshot",
            "-f", FULL_PATH,
            "-e",
            "-j",
            "-q", str(JPEG_QUALITY)
        ]
        
        print(f"Capturing screen to {FULL_PATH} with gnome-screenshot...")
        # Now, suppress stderr only for gnome-screenshot to keep it quiet
        capture_success = run_command(screenshot_command_args, suppress_stderr=True)

        if capture_success and os.path.exists(FULL_PATH) and os.path.getsize(FULL_PATH) > 0:
            print("Screenshot taken successfully.")

            # 2. Send the image to the receiver using curl
            curl_command_args = [
                "curl",
                "-s",
                "-X", "PUT",
                "--data-binary", f"@{FULL_PATH}",
                f"http://{RECEIVER_TAILSCALE_IP}:{RECEIVER_PORT}/{SCREENSHOT_NAME}"
            ]
            
            print(f"Sending image to {RECEIVER_TAILSCALE_IP}:{RECEIVER_PORT}...")
            # We don't suppress stderr for curl, so you'll see any network errors
            send_success = run_command(curl_command_args, suppress_stderr=False) 

            if send_success:
                print("Image sent successfully.")
            else:
                print("Failed to send image via curl.")
        else:
            print("Screenshot failed or was blocked. Ensure Michael is logged into a graphical session.")
            print("If running via SSH, make sure you used 'ssh -X' and that X11 forwarding is configured.")
            
        # 3. Delete the temporary screenshot file
        if os.path.exists(FULL_PATH):
            try:
                os.remove(FULL_PATH)
                print(f"Deleted temporary file: {FULL_PATH}")
            except OSError as e:
                print(f"Error deleting file {FULL_PATH}: {e}")
        else:
            print(f"File {FULL_PATH} did not exist to delete (already failed capture).")


        # Control frame rate
        end_time = time.time()
        elapsed_time = end_time - start_time
        sleep_time = DELAY_SECONDS - elapsed_time

        if sleep_time > 0:
            time.sleep(sleep_time)
        
        print(f"Frame processed in {elapsed_time:.2f}s. Sleeping for {max(0, sleep_time):.2f}s.")

if __name__ == "__main__":
    print("\nIMPORTANT: This script uses gnome-screenshot (X11/Wayland-Portal compatible).")
    print("Ensure Michael is LOGGED INTO THE GRAPHICAL DESKTOP (Zorin GUI).")
    print("Run this script from a TERMINAL WITHIN THAT GUI SESSION, or via SSH with X11 forwarding (-X flag).")
    print("To run in the background after starting: 'nohup python3 sender_script.py &' then close terminal.\n")
    send_screen_data()