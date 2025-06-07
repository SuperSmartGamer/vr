import subprocess
import os
import time
import sys

# --- Configuration ---
RECEIVER_TAILSCALE_IP = '100.96.244.18' # Your PC's Tailscale IP
RECEIVER_PORT = 8000 # This must match the port the receiver's HTTP server is listening on
FPS = 1 # Frames per second (1 or 2 is good for remote streaming)
JPEG_QUALITY = 60 # JPEG quality (0-100). 60-75 is a good balance for compression/quality.

CAPTURE_DIR = "/tmp" # Temporary directory for screenshots
SCREENSHOT_NAME = "remote_screen.jpeg" # Filename for the screenshot
FULL_PATH = os.path.join(CAPTURE_DIR, SCREENSHOT_NAME)

# Calculate delay in seconds for desired FPS
DELAY_SECONDS = 1 / FPS

def run_command(command_args, capture_output=False, print_output=False, suppress_stderr=True):
    """
    Helper function to run shell commands using subprocess.run().
    command_args: List of command and its arguments.
    capture_output: If True, stdout and stderr are captured and returned.
    print_output: If True, stdout is printed live.
    suppress_stderr: If True, stderr is redirected to /dev/null unless command fails.
    """
    # Explicitly copy the current environment to pass to the subprocess.
    # This is CRUCIAL for graphical applications like gnome-screenshot in an SSH -X session.
    current_env = os.environ.copy()

    stdout_pipe = subprocess.PIPE if capture_output or print_output else None
    stderr_pipe = subprocess.PIPE if capture_output or not suppress_stderr else subprocess.DEVNULL

    try:
        process = subprocess.Popen(command_args, stdout=stdout_pipe, stderr=stderr_pipe, text=True, env=current_env)
        stdout, stderr = process.communicate() # Wait for process to complete

        if print_output and stdout:
            print(f"Command STDOUT: {stdout.strip()}")

        if stderr:
            # Always print stderr if command failed, or if not suppressing
            if process.returncode != 0 or not suppress_stderr:
                print(f"Command STDERR: {stderr.strip()}")
            elif stdout: # If command succeeded but had unexpected stderr, print it
                print(f"Command unexpectedly produced STDERR: {stderr.strip()}")

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command_args, stdout, stderr)

        return stdout.strip() if capture_output else True

    except FileNotFoundError:
        print(f"ERROR: Command '{command_args[0]}' not found. Make sure it's installed and in your PATH.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"COMMAND FAILED (Exit Code {e.returncode}): {' '.join(e.cmd)}")
        print(f"STDOUT: {e.stdout.strip()}")
        print(f"STDERR: {e.stderr.strip()}")
        return False
    except Exception as e:
        print(f"AN UNEXPECTED ERROR OCCURRED during '{' '.join(command_args)}': {e}")
        return False

def check_dependencies():
    """
    Checks if gnome-screenshot and curl are available.
    """
    print("Checking dependencies...")
    # For 'which' command, we explicitly want its output, so capture it.
    if not run_command(["which", "gnome-screenshot"], capture_output=True, suppress_stderr=True):
        print("Error: 'gnome-screenshot' not found. Please install GNOME Screenshot (e.g., 'sudo apt install gnome-screenshot').")
        sys.exit(1)
    print("'gnome-screenshot' found.")

    if not run_command(["which", "curl"], capture_output=True, suppress_stderr=True):
        print("Error: 'curl' not found. Please install curl (e.g., 'sudo apt install curl').")
        sys.exit(1)
    print("'curl' found.")
    print("All dependencies checked successfully.")


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
            "-e", # Entire screen
            "-j", # JPEG format
            "-q", str(JPEG_QUALITY) # Quality
        ]
        
        print(f"Capturing screen to {FULL_PATH} with gnome-screenshot...")
        # Suppress stderr for gnome-screenshot as it can be noisy even when successful.
        capture_success = run_command(screenshot_command_args, suppress_stderr=True)

        if capture_success and os.path.exists(FULL_PATH) and os.path.getsize(FULL_PATH) > 0:
            print("Screenshot taken successfully.")

            # 2. Send the image to the receiver using curl
            curl_command_args = [
                "curl",
                "-s", # Silent mode (don't show progress meter)
                "-X", "PUT",
                "--data-binary", f"@{FULL_PATH}",
                f"http://{RECEIVER_TAILSCALE_IP}:{RECEIVER_PORT}/{SCREENSHOT_NAME}"
            ]
            
            print(f"Sending image to {RECEIVER_TAILSCALE_IP}:{RECEIVER_PORT}...")
            # Do NOT suppress stderr for curl, so you'll see any network errors.
            send_success = run_command(curl_command_args, suppress_stderr=False) 

            if send_success:
                print("Image sent successfully.")
            else:
                print("Failed to send image via curl.")
        else:
            print("Screenshot capture failed. This likely means:")
            print("  - Michael is not logged into his graphical desktop.")
            print("  - Your SSH session did not have X11 forwarding enabled/working ('ssh -X' was not used or failed).")
            print("  - The screen might be locked.")
            print("Please ensure Michael is logged in and your SSH -X setup is correct.")
            
        # 3. Delete the temporary screenshot file
        if os.path.exists(FULL_PATH):
            try:
                os.remove(FULL_PATH)
                print(f"Deleted temporary file: {FULL_PATH}")
            except OSError as e:
                print(f"Error deleting file {FULL_PATH}: {e}")
        else:
            print(f"File {FULL_PATH} did not exist to delete (likely due to failed capture).")


        # Control frame rate
        end_time = time.time()
        elapsed_time = end_time - start_time
        sleep_time = DELAY_SECONDS - elapsed_time

        if sleep_time > 0:
            time.sleep(sleep_time)
        
        print(f"Frame processed in {elapsed_time:.2f}s. Sleeping for {max(0, sleep_time):.2f}s.")

if __name__ == "__main__":
    print("\n----------------------------------------------------------------------")
    print("              TAILSCALE SCREEN SHARE SENDER SCRIPT")
    print("----------------------------------------------------------------------")
    print("This script captures Michael's live graphical screen.")
    print("1. **Michael MUST be LOGGED INTO THE ZORIN OS GRAPHICAL DESKTOP.**")
    print("2. **You MUST connect via SSH with X11 forwarding enabled (e.g., `ssh -X michael@<IP>`).**")
    print("   Verify by running `echo $DISPLAY` in your SSH session; it should show a value like `localhost:10.0`.")
    print("3. **DO NOT USE `sudo`** to run this Python script.")
    print("4. For background operation (recommended), use:")
    print("   `nohup python3 sender_script.py &` then you can close the SSH terminal.")
    print("----------------------------------------------------------------------\n")
    send_screen_data()