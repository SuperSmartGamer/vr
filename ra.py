#!/usr/bin/env python3
import os
import subprocess
import stat
import traceback

# Determine main directory (where this setup script resides)
MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(MAIN_DIR, "scripts")
LOG_FILE = os.path.join(MAIN_DIR, "console.log")
SERVICE_PATH = "/etc/systemd/system/tmate-persistent.service"

# Ensure directories exist
try:
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
except Exception as e:
    print(f"Error creating scripts directory {SCRIPTS_DIR}: {e}")
    exit(1)

# Logging helper
def log(message):
    try:
        with open(LOG_FILE, "a") as log_f:
            log_f.write(f"{message}\n")
    except Exception:
        pass  # If logging fails, avoid crashing

# Create a file only if it does not exist
def write_file_if_missing(path, content, executable=False):
    if os.path.exists(path):
        log(f"Skipping creation of {path}: already exists.")
        return
    try:
        with open(path, "w") as f:
            f.write(content)
        if executable:
            st = os.stat(path)
            os.chmod(path, st.st_mode | stat.S_IEXEC)
        log(f"Created {path}.")
    except Exception:
        log(f"Error creating {path}:\n{traceback.format_exc()}")

# Enable and start the systemd service if needed
def enable_and_start_service():
    try:
        # Reload daemon to pick up new or changed service file
        subprocess.run(["systemctl", "daemon-reload"], check=True)
    except Exception:
        log(f"Error reloading systemd:\n{traceback.format_exc()}")
        return

    # Check if service file exists
    if not os.path.exists(SERVICE_PATH):
        log(f"Service file {SERVICE_PATH} missing; cannot enable service.")
        return

    # Try enabling service
    try:
        subprocess.run(["systemctl", "enable", "tmate-persistent"], check=True)
        log("Service 'tmate-persistent' enabled.")
    except subprocess.CalledProcessError:
        log("Service 'tmate-persistent' may already be enabled (or enabling failed).")

    # Check if service is running
    try:
        subprocess.run(["systemctl", "is-active", "--quiet", "tmate-persistent"], check=True)
        log("Service 'tmate-persistent' is already running.")
    except subprocess.CalledProcessError:
        # Not running → start it
        try:
            subprocess.run(["systemctl", "start", "tmate-persistent"], check=True)
            log("Started service 'tmate-persistent'.")
        except Exception:
            log(f"Error starting service:\n{traceback.format_exc()}")

# === Script templates ===

# 1. tmate_script.py
tmate_script = f"""#!/usr/bin/env python3
import os
import traceback

log_path = "{LOG_FILE}"
def log_local(msg):
    try:
        with open(log_path, "a") as log_f:
            log_f.write(msg + "\\n")
    except:
        pass

try:
    os.system("apt update && apt install -y tmate")
    os.system("tmate -S /tmp/tmate.sock new-session -d")
    os.system("tmate -S /tmp/tmate.sock wait tmate-ready")
    os.system("tmate -S /tmp/tmate.sock display -p '#{{tmate_ssh}}' > /tmp/tmate.txt")
except Exception as e:
    log_local("Error in tmate_script.py:")
    log_local(str(e))
    log_local(traceback.format_exc())
"""

# 2. upload_to_r2.py
upload_to_r2 = f"""#!/usr/bin/env python3
import boto3
import traceback

log_path = "{LOG_FILE}"
def log_local(msg):
    try:
        with open(log_path, "a") as log_f:
            log_f.write(msg + "\\n")
    except:
        pass

ACCESS_KEY = 'db8efca097d2506714901db06ea81b97'
SECRET_KEY = '4a873df3ad2fdd9be894f779461fb2ab9def4202ea50afc42e9ecf029498d0fa'
ACCOUNT_ID = 'fd5b99900fc2700f1f893f9ee5d52c07'
BUCKET_NAME = 'my-bucket'
endpoint_url = f'https://{{ACCOUNT_ID}}.r2.cloudflarestorage.com'

try:
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
    )
    with open('/tmp/tmate.txt', 'rb') as f:
        s3.upload_fileobj(f, BUCKET_NAME, 'tmate.txt')
except Exception as e:
    log_local("Error in upload_to_r2.py:")
    log_local(str(e))
    log_local(traceback.format_exc())
"""

# 3. tmate_loop.sh
tmate_loop = f"""#!/bin/bash
LOG_FILE="{LOG_FILE}"
while true; do
  if [ ! -S /tmp/tmate.sock ]; then
    echo "$(date) - Socket missing; starting new tmate session" >> "$LOG_FILE"
    python3 "{os.path.join(SCRIPTS_DIR, 'tmate_script.py')}" || echo "$(date) - Error running tmate_script.py" >> "$LOG_FILE"
    python3 "{os.path.join(SCRIPTS_DIR, 'upload_to_r2.py')}" || echo "$(date) - Error running upload_to_r2.py" >> "$LOG_FILE"
  fi
  sleep 300
done
"""

# 4. systemd service unit
service_unit = f"""[Unit]
Description=Persistent tmate session
After=network.target

[Service]
ExecStart=/bin/bash {os.path.join(SCRIPTS_DIR, "tmate_loop.sh")}
Restart=always
User=root
StandardOutput=append:{LOG_FILE}
StandardError=append:{LOG_FILE}

[Install]
WantedBy=multi-user.target
"""

# === Create or skip files ===
write_file_if_missing(os.path.join(SCRIPTS_DIR, "tmate_script.py"), tmate_script)
write_file_if_missing(os.path.join(SCRIPTS_DIR, "upload_to_r2.py"), upload_to_r2)
write_file_if_missing(os.path.join(SCRIPTS_DIR, "tmate_loop.sh"), tmate_loop, executable=True)
write_file_if_missing(SERVICE_PATH, service_unit)

# === Enable and start service ===
enable_and_start_service()

log("setup_tmate_access.py finished successfully.")
