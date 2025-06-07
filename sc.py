#!/usr/bin/env python3
import subprocess
import time
import io
import logging
import sys
import requests
from PIL import Image, UnidentifiedImageError

# ─── CONFIG ────────────────────────────────────────────────────────────────────
dest_url = "http://100.81.157.107:8000/frame.jpg"
interval = 0.5  # seconds between captures
log_file = "sc.log"
verbose = True  # set False to disable console prints
jpeg_quality = 75
screenshot_path = "/tmp/frame.png"
# ────────────────────────────────────────────────────────────────────────────────

# ─── LOGGING SETUP ──────────────────────────────────────────────────────────────
def setup_logging():
    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    if verbose:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        console.setFormatter(formatter)
        logging.getLogger('').addHandler(console)

# ─── CLEANUP TEMP FILE ──────────────────────────────────────────────────────────
def cleanup():
    try:
        subprocess.run(["rm", "-f", screenshot_path], check=False)
        logging.debug(f"Deleted temp file {screenshot_path}")
    except Exception as e:
        logging.warning(f"Failed to delete {screenshot_path}: {e}")

# ─── CAPTURE SCREENSHOT ─────────────────────────────────────────────────────────
def take_screenshot():
    logging.debug("Capturing screenshot...")
    try:
        env = {"DISPLAY": ":0"}
        subprocess.run(
            ["gnome-screenshot", "-f", screenshot_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
        )
        logging.info("Screenshot captured.")
        return True
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode().strip()
        logging.error(f"Screenshot failed: {err}")
        return False

# ─── ENCODE AND SEND ────────────────────────────────────────────────────────────
def encode_and_send():
    logging.debug("Opening screenshot and converting to JPEG...")
    try:
        img = Image.open(screenshot_path)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=jpeg_quality)
        buf.seek(0)
        logging.debug("JPEG encoded successfully. Sending frame...")
        response = requests.put(dest_url, data=buf.read(), timeout=10)
        response.raise_for_status()
        logging.info(f"Frame sent: {response.status_code}")
        return True
    except FileNotFoundError:
        logging.error("Temp screenshot file not found.")
    except UnidentifiedImageError:
        logging.error("Screenshot image could not be opened.")
    except requests.RequestException as e:
        logging.error(f"Failed to send frame: {e}")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
    return False

# ─── MAIN LOOP ──────────────────────────────────────────────────────────────────
def main():
    setup_logging()
    logging.info("Starting screenshot stream loop")
    while True:
        if take_screenshot():
            encode_and_send()
        cleanup()
        time.sleep(interval)

if __name__ == "__main__":
    main()
