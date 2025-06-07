#!/usr/bin/env python3
import subprocess, time, io, logging
import requests
from PIL import Image, UnidentifiedImageError

# configure this
dest_url = "http://100.96.244.18:8000/frame.jpg"
interval = 0.5   # seconds
log_file = "sc.log"

# set up logging
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def capture_and_send():
    # 1) grab a PNG to temp
    try:
        subprocess.run(
            ["gnome-screenshot", "-f", "/tmp/frame.png"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        logging.error(f"screenshot failed: {e.stderr.decode().strip()}")
        return

    # 2) open and re-encode as JPEG in-memory
    try:
        img = Image.open("/tmp/frame.png")
    except (FileNotFoundError, UnidentifiedImageError) as e:
        logging.error(f"loading PNG failed: {e}")
        return

    buf = io.BytesIO()
    try:
        img.save(buf, format="JPEG", quality=75)
    except Exception as e:
        logging.error(f"JPEG encoding failed: {e}")
        return
    buf.seek(0)

    # 3) stream via HTTP PUT
    try:
        resp = requests.put(dest_url, data=buf.read(), timeout=5)
        resp.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"upload failed: {e}")
        return

def main():
    logging.info("Starting screenshot stream")
    while True:
        capture_and_send()
        time.sleep(interval)

if __name__ == "__main__":
    main()
