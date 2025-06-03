import threading
import subprocess
import time
import sys
import logging
import traceback
import upload_to_r2 from upload

# Configure logging to write errors to console.log
logging.basicConfig(
    filename='console.log',
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def install_requirements():
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT
        )
    except Exception:
        logger.error(
            "Failed to install requirements.txt:\n%s",
            traceback.format_exc()
        )

def repeat_function():
    while True:
        try:
            # Place your periodic task here
            upload_to_r2("thing.txt")
            upload_to_r2("console.log")

            print("Repeating task")
        except Exception:
            logger.error(
                "Error in repeat_function:\n%s",
                traceback.format_exc()
            )
        finally:
            time.sleep(60)

def run_script(script_path):
    while True:
        try:
            proc = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            # Wait for the child process to exit
            _, stderr = proc.communicate()
            if proc.returncode != 0:
                logger.error(
                    "Script '%s' exited with code %d. Stderr:\n%s",
                    script_path,
                    proc.returncode,
                    stderr.decode(errors='ignore')
                )
        except Exception:
            logger.error(
                "Error launching script '%s':\n%s",
                script_path,
                traceback.format_exc()
            )
        # Brief pause before attempting to restart
        time.sleep(5)

def main():
    install_requirements()

    scripts = ["kg.py"]  # replace with your script filenames

    # Start each script in its own thread, auto-restarting on crash
    for s in scripts:
        t = threading.Thread(
            target=run_script,
            args=(s,),
            daemon=True
        )
        t.start()

    # Start the repeating function in its own thread
    t_repeat = threading.Thread(
        target=repeat_function,
        daemon=True
    )
    t_repeat.start()

    # Keep the main thread alive indefinitely
    try:
        while True:
            time.sleep(1)
    except Exception:
        logger.error(
            "Unexpected error in main loop:\n%s",
            traceback.format_exc()
        )
        # If main loop crashes, prevent exit by restarting it
        main()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.error(
            "Fatal error in supervisor script:\n%s",
            traceback.format_exc()
        )
        # Prevent the script from exiting
        while True:
            time.sleep(60)
