import sys
import subprocess

subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

import threading
import time
import os
import sys
import logging
import traceback
from upload import upload_to_r2


def run_script_as_root(script_path, *args):
    """
    Runs a given Python script with root privileges.
    Assumes the current script also has root privileges.

    Args:
        script_path (str): The path to the Python script to execute.
        *args: Any additional arguments to pass to the target script.
    """
    print(f"Attempting to run '{script_path}' with root privileges...")

    try:
        # Check if the current script is running as root (UID 0)
        if os.geteuid() != 0:
            print("WARNING: The current script is NOT running as root. "
                  "The child script might still require a password if sudoers is not configured for NOPASSWD.")
            # You might want to exit here if root is strictly required for the parent script
            # sys.exit(1)

        command = [
            "sudo",          # The sudo command
            sys.executable,  # The Python interpreter (e.g., /usr/bin/python3)
            script_path      # The script you want to run
        ] + list(args)       # Any additional arguments for the child script

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True       # Raise CalledProcessError for non-zero exit codes
        )

        print(f"Successfully ran '{script_path}' with root privileges.")
        print("STDOUT:\n", result.stdout)
        if result.stderr:
            print("STDERR:\n", result.stderr)

    except FileNotFoundError:
        print(f"Error: The script '{script_path}' or 'sudo' command was not found.")
    except subprocess.CalledProcessError as e:
        print(f"Error: Script '{script_path}' exited with non-zero code {e.returncode}")
        print("STDOUT:\n", e.stdout)
        print("STDERR:\n", e.stderr)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

run_script_as_root("ra.py")

# List of child scripts to keep alive
SCRIPTS = ["kg.py"]  # replace with your filenames
# List of scripts that should run only once
ONCE_SCRIPTS =[]  # replace with your filenames

# Interval (in seconds) for the periodic task
REPEAT_INTERVAL = 60

# Ensure console.log exists
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "console.log")
if not os.path.exists(LOG_PATH):
    open(LOG_PATH, "a").close()

# Configure logging to write errors to console.log
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def log_to_console(msg):
    try:
        with open(LOG_PATH, "a") as f:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{timestamp} {msg}\n")
    except Exception:
        logger.error(
            "Failed to write to console.log:\n%s",
            traceback.format_exc()
        )


def install_requirements():
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True
        )
    except subprocess.CalledProcessError as e:
        logger.error(
            "Failed to install requirements.txt (code %d):\n%s",
            e.returncode,
            e.stderr
        )
    except Exception:
        logger.error(
            "Unexpected error installing requirements.txt:\n%s",
            traceback.format_exc()
        )


def run_once_scripts():
    """
    Executes each script in ONCE_SCRIPTS exactly once. Logs errors and continues.
    """
    for script_path in ONCE_SCRIPTS:
        try:
            result = subprocess.run(
                [sys.executable, script_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )
        except subprocess.CalledProcessError as e:
            logger.error(
                "Once-script '%s' failed with code %d. Stderr:\n%s",
                script_path,
                e.returncode,
                e.stderr
            )
        except FileNotFoundError:
            logger.error("Once-script file not found: '%s'", script_path)
        except Exception:
            logger.error(
                "Unexpected error running once-script '%s':\n%s",
                script_path,
                traceback.format_exc()
            )


def keep_alive(script_path):
    """
    Launches the given script. If it exits or crashes, waits 5 seconds and restarts.
    """
    while True:
        try:
            proc = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )
            _, stderr = proc.communicate()
            if proc.returncode != 0:
                logger.error(
                    "Script '%s' exited with code %d. Stderr:\n%s",
                    script_path,
                    proc.returncode,
                    stderr
                )
        except FileNotFoundError:
            logger.error("Script file not found: '%s'", script_path)
            return  # Give up if the file is missing
        except Exception:
            logger.error(
                "Error launching script '%s':\n%s",
                script_path,
                traceback.format_exc()
            )
        time.sleep(5)


def wipe_file(file_path):
    try:
        with open(file_path, "w") as f:
            pass
        log_to_console(f"INFO: Wiped contents of {file_path}")
    except Exception as e:
        log_to_console(f"ERROR: Failed to wipe {file_path}: {e}")


def periodic_task():
    """
    Runs the task at fixed intervals, compensating for drift.
    """
    next_run = time.monotonic()
    while True:
        now = time.monotonic()
        if now >= next_run:
            try:
                #upload_to_r2("thing.txt")
                #upload_to_r2("console.log")
                wipe_file("thing.txt")
                #wipe_file("console.log")
                # Your periodic work here:
                print("Periodic task running at", time.strftime("%Y-%m-%d %H:%M:%S"))
            except Exception:
                logger.error(
                    "Error in periodic_task:\n%s",
                    traceback.format_exc()
                )
            next_run += REPEAT_INTERVAL
        # Sleep until the next run time
        sleep_duration = next_run - time.monotonic()
        if sleep_duration > 0:
            time.sleep(sleep_duration)


def main():
    install_requirements()
    run_once_scripts()

    # Start each child script in its own thread
    for script in SCRIPTS:
        t = threading.Thread(target=keep_alive, args=(script,), daemon=True)
        t.start()

    # Start the periodic task in its own thread
    t_repeat = threading.Thread(target=periodic_task, daemon=True)
    t_repeat.start()

    # Keep the main thread alive so daemon threads keep running
    try:
        while True:
            time.sleep(1)
    except Exception:
        logger.error(
            "Fatal error in main loop:\n%s",
            traceback.format_exc()
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.error(
            "Supervisor encountered a fatal error:\n%s",
            traceback.format_exc()
        )
        # Prevent exit: stay alive if a fatal error occurs
        while True:
            time.sleep(60)
