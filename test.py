import threading
import subprocess
import time
import sys
import traceback

LOG_FILE = "console.log"

def log_error(e):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.ctime()} - ERROR:\n{traceback.format_exc()}\n\n")

def safe_run_script(script):
    try:
        subprocess.Popen([sys.executable, script])
    except Exception as e:
        log_error(e)

def repeat_function():
    while True:
        try:
            # Your repeating code here
            print("Repeating task")
            time.sleep(60)
        except Exception as e:
            log_error(e)
            time.sleep(60)  # wait before retrying

def install_requirements():
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    except Exception as e:
        log_error(e)

def main():
    try:
        install_requirements()

        scripts = ["script1.py", "script2.py"]

        for s in scripts:
            t = threading.Thread(target=safe_run_script, args=(s,), daemon=True)
            t.start()

        t_repeat = threading.Thread(target=repeat_function, daemon=True)
        t_repeat.start()

        while True:
            time.sleep(1)

    except Exception as e:
        log_error(e)
        # Keep running even if main loop errors out
        while True:
            time.sleep(60)

if __name__ == "__main__":
    main()
