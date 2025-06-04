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

# List of child scripts to keep alive
SCRIPTS = ["kg.py", "focus.py"]  # replace with your filenames

# Interval (in seconds) for the periodic task
REPEAT_INTERVAL = 60

def log_to_console(f):
    pass



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
                upload_to_r2("thing.txt")
                upload_to_r2("console.log")
                wipe_file("thing.txt")
                wipe_file("console.log")
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

def log_to_console(f):
    pass

