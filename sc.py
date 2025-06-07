#!/usr/bin/env python3
import subprocess, time, io, logging
import requests
from PIL import Image, UnidentifiedImageError

# configure this
dest_url = "http://100.96.244.18:8000/frame.jpg"
interval = 0.5   # seconds
log_file = "sc.log"

def setup_logging():
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
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        buf.seek(0)
    except (FileNotFoundError, UnidentifiedImageError) as e:
        logging.error(f"loading or encoding PNG failed: {e}")
        _cleanup()
        return
    except Exception as e:
        logging.error(f"JPEG encoding failed: {e}")
        _cleanup()
        return

    # remove the PNG after encoding
    _cleanup()

    # 3) stream via HTTP PUT
    try:
        resp = requests.put(dest_url, data=buf.read(), timeout=5)
        resp.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"upload failed: {e}")
        return


def _cleanup():
    # remove temporary files
    try:
        subprocess.run(["rm", "-f", "/tmp/frame.png"], check=False)
    except Exception as e:
        logging.warning(f"cleanup failed: {e}")


def main():
    setup_logging()
    logging.info("Starting screenshot stream")
    while True:
        capture_and_send()
        time.sleep(interval)

if __name__ == "__main__":
    main()
