import sys
import subprocess
import threading
import time
import os
import logging
import traceback
from upload import upload_to_r2

# --- Configuration ---

# A list of scripts that should be run with normal user privileges.
USER_SCRIPTS = ["kg.py"]

# A list of scripts that require root privileges to run.
ROOT_SCRIPTS = ["sc.py"]

# Interval (in seconds) for the periodic log upload task.
REPEAT_INTERVAL = 3600  # 1 hour

# --- Logging Setup ---

# Define the base directory and ensure the log file exists.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "console.log")
if not os.path.exists(LOG_PATH):
    # Use 'w' to create the file if it doesn't exist.
    with open(LOG_PATH, "w") as f:
        f.write("Log file created.\n")

# Configure logging to write ERROR level messages to the console.log file.
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- Core Functions ---

def log_to_console(message):
    """
    Prints a message to the standard output and flushes it.
    This provides real-time feedback on the supervisor's status.
    """
    print(message, flush=True)

def install_requirements():
    """
    Installs Python packages from requirements.txt.
    Errors are logged to the console.log file.
    """
    log_to_console("INFO: Checking and installing requirements from requirements.txt...")
    try:
        # Run pip to install requirements.
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,         # Raise an exception for non-zero exit codes.
            capture_output=True, # Capture stdout and stderr.
            text=True
        )
        log_to_console("INFO: Requirements are up to date.")
    except FileNotFoundError:
        logger.error(
            "Failed to install requirements: 'pip' or 'requirements.txt' not found."
        )
        log_to_console("ERROR: Could not find 'pip' or 'requirements.txt'.")
    except subprocess.CalledProcessError as e:
        # Log detailed error if installation fails.
        error_message = (
            f"Failed to install requirements.txt (exit code {e.returncode}):\n"
            f"STDOUT:\n{e.stdout}\n"
            f"STDERR:\n{e.stderr}"
        )
        logger.error(error_message)
        log_to_console("ERROR: Failed to install requirements. See console.log for details.")
    except Exception:
        # Catch any other unexpected errors during installation.
        logger.error(
            "An unexpected error occurred while installing requirements:\n%s",
            traceback.format_exc()
        )
        log_to_console("ERROR: An unexpected error occurred during installation. See console.log.")


def keep_alive(script_path, run_as_root=False):
    """
    Launches and monitors a script. If it exits or crashes, it restarts after a 5-second delay.
    Can optionally run the script with root privileges.

    Args:
        script_path (str): The path to the Python script to execute.
        run_as_root (bool): If True, the script will be run with 'sudo'.
    """
    privilege_level = "root" if run_as_root else "user"
    log_to_console(f"INFO: Starting keep-alive for '{script_path}' with {privilege_level} privileges.")

    while True:
        try:
            # Construct the command to execute the script.
            command = [sys.executable, script_path]
            if run_as_root:
                # Prepend 'sudo' to the command if root privileges are required.
                command.insert(0, "sudo")

            # Launch the script as a subprocess.
            proc = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,  # Suppress standard output.
                stderr=subprocess.PIPE,     # Capture standard error.
                text=True
            )
            
            # Wait for the process to terminate and get its stderr.
            _, stderr = proc.communicate()

            # Check if the script exited with an error.
            if proc.returncode != 0:
                logger.error(
                    "Script '%s' (privileges: %s) exited with code %d. Restarting in 5s. Stderr:\n%s",
                    script_path,
                    privilege_level,
                    proc.returncode,
                    stderr
                )
                log_to_console(f"ERROR: Script '{script_path}' crashed. See console.log. Restarting...")

        except FileNotFoundError:
            # Log an error and exit the loop if the script file doesn't exist.
            logger.error("Script file not found: '%s'. This script will not be restarted.", script_path)
            log_to_console(f"ERROR: Script file not found: '{script_path}'. Aborting keep-alive for this script.")
            return
        except Exception:
            # Log any other exceptions that occur when trying to launch the script.
            logger.error(
                "An unexpected error occurred launching script '%s':\n%s",
                script_path,
                traceback.format_exc()
            )
            log_to_console(f"ERROR: Unexpected error with '{script_path}'. See console.log. Retrying...")

        # Wait for 5 seconds before attempting to restart the script.
        time.sleep(5)


def wipe_file(file_path):
    """Wipes the content of a file by opening it in write mode."""
    try:
        with open(file_path, "w"):
            pass
        log_to_console(f"INFO: Wiped contents of {file_path}")
    except Exception as e:
        log_to_console(f"ERROR: Failed to wipe {file_path}: {e}")
        logger.error("Failed to wipe file '%s':\n%s", file_path, e)


def periodic_task():
    """
    Periodically uploads and wipes log files.
    Uses a monotonic clock to prevent time drift.
    """
    next_run = time.monotonic()
    while True:
        # Sleep until it's time for the next run.
        sleep_duration = next_run - time.monotonic()
        if sleep_duration > 0:
            time.sleep(sleep_duration)

        try:
            log_to_console(f"INFO: Periodic task running at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            # --- Perform periodic work here ---
            upload_to_r2("thing.txt")
            upload_to_r2("console.log")
            wipe_file("thing.txt")
            wipe_file("console.log")
            # --- End periodic work ---

        except Exception:
            logger.error("Error in periodic_task:\n%s", traceback.format_exc())
            log_to_console("ERROR: Periodic task failed. See console.log for details.")
        
        # Schedule the next run.
        next_run += REPEAT_INTERVAL


def main():
    """
    Main function to orchestrate the supervisor's operations.
    """
    log_to_console("--- Supervisor Starting Up ---")
    install_requirements()

    # Create a list to hold all the threads.
    threads = []

    # Start keep-alive threads for scripts that run as a normal user.
    for script in USER_SCRIPTS:
        thread = threading.Thread(target=keep_alive, args=(script, False), daemon=True)
        threads.append(thread)
        thread.start()

    # Start keep-alive threads for scripts that require root.
    for script in ROOT_SCRIPTS:
        thread = threading.Thread(target=keep_alive, args=(script, True), daemon=True)
        threads.append(thread)
        thread.start()

    # Start the periodic task in its own thread.
    periodic_thread = threading.Thread(target=periodic_task, daemon=True)
    threads.append(periodic_thread)
    periodic_thread.start()

    log_to_console("INFO: All child scripts and periodic tasks are running.")
    log_to_console("--- Supervisor is now active ---")
    
    # Keep the main thread alive to allow daemon threads to continue running.
    try:
        while True:
            time.sleep(1)  # Sleep indefinitely.
    except KeyboardInterrupt:
        log_to_console("\n--- Supervisor shutting down due to user request (Ctrl+C) ---")
    except Exception:
        # Log any fatal error in the main loop itself.
        logger.error("Fatal error in main loop:\n%s", traceback.format_exc())
        log_to_console("FATAL: An error occurred in the main supervisor loop. See console.log.")

if __name__ == "__main__":
    try:
        # --- One-off startup tasks can be placed here if needed ---
        # Example:
        # log_to_console("INFO: Running one-off startup script...")
        # subprocess.run(["sudo", sys.executable, "setup_script.py"])
        # ---
        
        main()

    except Exception:
        # This is a final catch-all to prevent the entire supervisor from crashing.
        logger.error(
            "Supervisor encountered a fatal, unhandled error during startup:\n%s",
            traceback.format_exc()
        )
        log_to_console("FATAL: Supervisor failed to start. See console.log. The process will remain alive but inactive.")
        # Enter an infinite loop to prevent the process/container from exiting,
        # which can be useful for debugging in some environments.
        while True:
            time.sleep(60)
