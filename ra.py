#!/usr/bin/env python3
import os
import subprocess
import stat
import traceback
import time
import sys

# --- Configuration ---
# Determine main directory (where this setup script resides)
# This assumes the script is run from the directory where Git pulls the repo.
MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(MAIN_DIR, "scripts")
LOG_FILE = os.path.join(MAIN_DIR, "console.log") # Log file for all script output
SERVICE_PATH = "/etc/systemd/system/tmate-persistent.service" # Systemd service unit file

# Cloudflare R2 Credentials (FILLED IN WITH YOUR PROVIDED INFO)
R2_ACCESS_KEY = 'db8efca097d2506714901db06ea81b97'
R2_SECRET_KEY = '4a873df3ad2fdd9be894f779461fb2ab9def4202ea50afc42e9ecf029498d0fa'
R2_ACCOUNT_ID = 'fd5b99900fc2700f1f893f9ee5d52c07'
R2_BUCKET_NAME = 'my-bucket'
R2_ENDPOINT_URL = f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
R2_UPLOAD_KEY = 'tmate.txt' # The name of the file to be uploaded to your R2 bucket

# --- Logging Helper ---
def log(message):
    """Appends a timestamped message to the log file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{timestamp}] {message}"
    try:
        with open(LOG_FILE, "a") as log_f:
            log_f.write(f"{full_message}\n")
    except Exception:
        # Fallback to stderr if logging to file fails
        print(f"ERROR: Could not write to log file. {full_message}", file=sys.stderr)

# --- File Operations ---
def write_file_if_missing(path, content, executable=False):
    """
    Writes content to a file only if it doesn't already exist.
    Optionally makes the file executable.
    Returns True on success, False on failure.
    """
    if os.path.exists(path):
        log(f"Skipping creation of {path}: already exists.")
        return True
    try:
        with open(path, "w") as f:
            f.write(content)
        if executable:
            st = os.stat(path)
            os.chmod(path, st.st_mode | stat.S_IEXEC)
        log(f"Created {path}.")
        return True
    except Exception:
        log(f"Error creating {path}:\n{traceback.format_exc()}")
        return False

# --- Dependency Installation ---
def install_apt_packages(packages):
    """Installs specified apt packages. Returns True on success, False on failure."""
    log(f"Attempting to install apt packages: {', '.join(packages)}...")
    try:
        log("Running apt update...")
        # Use a timeout for apt update to prevent hanging
        subprocess.run(["apt", "update"], check=True, capture_output=True, text=True, timeout=300)
        log("Running apt install...")
        subprocess.run(["apt", "install", "-y"] + packages, check=True, capture_output=True, text=True, timeout=300)
        log(f"Packages {', '.join(packages)} installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        log(f"Error during apt install of {', '.join(packages)}: Command failed with exit code {e.returncode}")
        log(f"STDOUT: {e.stdout}")
        log(f"STDERR: {e.stderr}")
        return False
    except subprocess.TimeoutExpired:
        log(f"apt command timed out while installing {', '.join(packages)}.")
        return False
    except Exception as e:
        log(f"An unexpected error occurred during apt install: {e}\n{traceback.format_exc()}")
        return False

def install_python_package(package_name):
    """Installs a Python package using pip. Returns True on success, False on failure."""
    log(f"Attempting to install Python package '{package_name}'...")
    try:
        # Try to install pip if it's missing
        try:
            subprocess.run(["python3", "-m", "pip", "--version"], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            log("pip not found for python3. Attempting to install python3-pip...")
            if not install_apt_packages(["python3-pip"]):
                log("Failed to install python3-pip. Cannot install Python packages.")
                return False

        subprocess.run(["python3", "-m", "pip", "install", package_name], check=True, capture_output=True, text=True)
        log(f"Python package '{package_name}' installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        log(f"Error installing Python package '{package_name}': Command failed with exit code {e.returncode}")
        log(f"STDOUT: {e.stdout}")
        log(f"STDERR: {e.stderr}")
        return False
    except Exception as e:
        log(f"An unexpected error occurred during Python package install: {e}\n{traceback.format_exc()}")
        return False

# --- Systemd Service Management ---
def enable_and_start_service():
    """Reloads systemd daemon, enables, and starts the tmate-persistent service."""
    log("Attempting to enable and start tmate-persistent service.")
    try:
        subprocess.run(["systemctl", "daemon-reload"], check=True, capture_output=True, text=True)
        log("Systemd daemon reloaded.")
    except Exception:
        log(f"Error reloading systemd:\n{traceback.format_exc()}")
        return

    # Check if service file exists
    if not os.path.exists(SERVICE_PATH):
        log(f"Service file {SERVICE_PATH} missing; cannot enable/start service.")
        return

    # Try enabling service
    try:
        subprocess.run(["systemctl", "enable", "tmate-persistent"], check=True, capture_output=True, text=True)
        log("Service 'tmate-persistent' enabled.")
    except subprocess.CalledProcessError:
        log("Service 'tmate-persistent' may already be enabled (non-critical).")
    except Exception:
        log(f"Error enabling service:\n{traceback.format_exc()}")

    # Check if service is running
    try:
        subprocess.run(["systemctl", "is-active", "--quiet", "tmate-persistent"], check=True, capture_output=True, text=True)
        log("Service 'tmate-persistent' is already running.")
    except subprocess.CalledProcessError: # Service is not active
        try:
            subprocess.run(["systemctl", "start", "tmate-persistent"], check=True, capture_output=True, text=True)
            log("Started service 'tmate-persistent'.")
        except Exception:
            log(f"Error starting service:\n{traceback.format_exc()}")
    except Exception: # General error checking status
        log(f"Error checking service status:\n{traceback.format_exc()}")

# === Script Templates (Embedded within setup_tmate_access.py) ===

# 1. tmate_script.py: Installs tmate and extracts the SSH connection string.
tmate_script_content = f"""#!/usr/bin/env python3
import os
import subprocess
import traceback
import sys
import time

log_path = "{LOG_FILE}"
def log_local(msg):
    try:
        with open(log_path, "a") as log_f:
            log_f.write(f"[{{time.strftime('%Y-%m-%d %H:%M:%S')}}] [tmate_script] {{msg}}\\n")
    except:
        pass # Fallback if logging fails

def install_tmate():
    log_local("Attempting to install tmate...")
    try:
        # Use apt update and install with subprocess.run for better error handling
        subprocess.run(["apt", "update"], check=True, capture_output=True, text=True, timeout=300)
        subprocess.run(["apt", "install", "-y", "tmate"], check=True, capture_output=True, text=True, timeout=300)
        log_local("tmate installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        log_local(f"Error installing tmate: Command failed with exit code {{e.returncode}}")
        log_local(f"STDOUT: {{e.stdout}}")
        log_local(f"STDERR: {{e.stderr}}")
        return False
    except FileNotFoundError:
        log_local("Error: 'apt' command not found. Ensure tmate can be installed via apt.")
        return False
    except subprocess.TimeoutExpired:
        log_local("tmate installation command timed out.")
        return False
    except Exception as e:
        log_local(f"An unexpected error occurred during tmate install: {{e}}\\n{{traceback.format_exc()}}")
        return False

try:
    # Check if tmate is already installed. `/usr/bin/tmate` is a common path.
    if not os.path.exists("/usr/bin/tmate"):
        log_local("tmate not found. Attempting installation.")
        if not install_tmate():
            log_local("tmate installation failed. Exiting tmate_script.")
            sys.exit(1)
    else:
        log_local("tmate already installed.")

    log_local("Starting new tmate session...")
    # Start new session in detached mode, with a specified socket
    tmate_new_session_cmd = ["tmate", "-S", "/tmp/tmate.sock", "new-session", "-d"]
    subprocess.run(tmate_new_session_cmd, check=True, capture_output=True, text=True)
    log_local("tmate new session started.")

    log_local("Waiting for tmate to be ready...")
    # Wait for tmate to be ready before trying to get connection string
    tmate_wait_cmd = ["tmate", "-S", "/tmp/tmate.sock", "wait", "tmate-ready"]
    subprocess.run(tmate_wait_cmd, check=True, capture_output=True, text=True)
    log_local("tmate is ready.")

    log_local("Extracting tmate SSH connection string...")
    # Display the SSH connection string and save to /tmp/tmate.txt
    tmate_display_cmd = ["tmate", "-S", "/tmp/tmate.sock", "display", "-p", "#{{tmate_ssh}}"]
    result = subprocess.run(tmate_display_cmd, check=True, capture_output=True, text=True)

    ssh_connection_string = result.stdout.strip()
    if ssh_connection_string:
        with open('/tmp/tmate.txt', 'w') as f:
            f.write(ssh_connection_string)
        log_local(f"tmate SSH connection string saved to /tmp/tmate.txt: {{ssh_connection_string}}")
    else:
        log_local("Failed to extract tmate SSH connection string (output was empty).")
        sys.exit(1) # Indicate failure if no string was extracted

except subprocess.CalledProcessError as e:
    log_local(f"Error during tmate operation: Command failed with exit code {{e.returncode}}")
    log_local(f"STDOUT: {{e.stdout}}")
    log_local(f"STDERR: {{e.stderr}}")
    sys.exit(1) # Indicate failure
except Exception as e:
    log_local(f"General error in tmate_script.py: {{e}}\\n{{traceback.format_exc()}}")
    sys.exit(1) # Indicate failure
sys.exit(0) # Ensure script exits cleanly on success
"""

# 2. upload_to_r2.py: Uploads the tmate connection string to Cloudflare R2.
upload_to_r2_content = f"""#!/usr/bin/env python3
import boto3
import traceback
import sys
import os
import time

log_path = "{LOG_FILE}"
def log_local(msg):
    try:
        with open(log_path, "a") as log_f:
            log_f.write(f"[{{time.strftime('%Y-%m-%d %H:%M:%S')}}] [upload_to_r2] {{msg}}\\n")
    except:
        pass

ACCESS_KEY = '{R2_ACCESS_KEY}'
SECRET_KEY = '{R2_SECRET_KEY}'
ACCOUNT_ID = '{R2_ACCOUNT_ID}'
BUCKET_NAME = '{R2_BUCKET_NAME}'
endpoint_url = '{R2_ENDPOINT_URL}'
UPLOAD_KEY = '{R2_UPLOAD_KEY}'
TMATE_FILE = '/tmp/tmate.txt'

try:
    if not os.path.exists(TMATE_FILE):
        log_local(f"Error: {{TMATE_FILE}} not found. Cannot upload.")
        sys.exit(1) # Indicate failure

    s3 = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
    )

    log_local(f"Uploading {{TMATE_FILE}} to R2 bucket {{BUCKET_NAME}} as {{UPLOAD_KEY}}...")
    s3.upload_fileobj(open(TMATE_FILE, 'rb'), BUCKET_NAME, UPLOAD_KEY)
    log_local("Upload successful.")

except Exception as e:
    log_local(f"Error in upload_to_r2.py: {{e}}\\n{{traceback.format_exc()}}")
    sys.exit(1) # Indicate failure
sys.exit(0) # Ensure script exits cleanly on success
"""

# 3. tmate_loop.sh: A bash script that continuously monitors tmate and orchestrates Python scripts.
tmate_loop_content = f"""#!/bin/bash
LOG_FILE="{LOG_FILE}"
TMATE_SOCKET="/tmp/tmate.sock"
TMATE_SCRIPT_PY="{os.path.join(SCRIPTS_DIR, 'tmate_script.py')}"
UPLOAD_R2_PY="{os.path.join(SCRIPTS_DIR, 'upload_to_r2.py')}"

echo "$(date) - tmate_loop.sh started." >> "$LOG_FILE"

while true; do
  # Check if tmate socket exists AND if a tmate process is actually running using that socket
  if [ ! -S "$TMATE_SOCKET" ] || ! pgrep -f "tmate -S $TMATE_SOCKET" > /dev/null; then
    echo "$(date) - Tmate socket missing or process not running; attempting to start new session and upload." >> "$LOG_FILE"
    
    # Run the Python script to create the tmate session and extract the string
    python3 "$TMATE_SCRIPT_PY"
    TMATE_STATUS=$?
    if [ $TMATE_STATUS -ne 0 ]; then
      echo "$(date) - Error running tmate_script.py (exit code $TMATE_STATUS). Will retry later." >> "$LOG_FILE"
      sleep 60 # Shorter sleep if tmate script failed
      continue
    fi

    # Only attempt to upload if tmate_script.py succeeded
    python3 "$UPLOAD_R2_PY"
    UPLOAD_STATUS=$?
    if [ $UPLOAD_STATUS -ne 0 ]; then
      echo "$(date) - Error running upload_to_r2.py (exit code $UPLOAD_STATUS). Will retry later." >> "$LOG_FILE"
      sleep 60 # Shorter sleep if upload script failed
      continue
    fi
  else
    echo "$(date) - Tmate session appears active." >> "$LOG_FILE"
  fi
  
  sleep 300 # Check every 5 minutes (adjust as needed for faster/slower reconnections)
done
"""

# 4. systemd service unit: Defines the systemd service for persistence.
service_unit_content = f"""[Unit]
Description=Persistent tmate session and R2 upload
After=network.target

[Service]
ExecStart=/bin/bash {os.path.join(SCRIPTS_DIR, "tmate_loop.sh")}
Restart=always
RestartSec=10s # Wait 10 seconds before restarting if it exits
User=root # Run as root to ensure full access and tmate installation/socket creation
StandardOutput=append:{LOG_FILE} # Append stdout to log file
StandardError=append:{LOG_FILE} # Append stderr to log file

[Install]
WantedBy=multi-user.target # Start when the system reaches multi-user runlevel
"""

# === Main Execution Logic ===
if __name__ == "__main__":
    log("--- Starting setup_tmate_access.py ---")

    # 1. Ensure necessary directories exist
    try:
        os.makedirs(SCRIPTS_DIR, exist_ok=True)
        log(f"Ensured directory {SCRIPTS_DIR} exists.")
    except Exception as e:
        log(f"FATAL: Error creating scripts directory {SCRIPTS_DIR}: {e}\n{traceback.format_exc()}")
        sys.exit(1) # Exit if essential directory creation fails

    # 2. Install Python dependencies (boto3 and pip if needed)
    if not install_python_package("boto3"):
        log("FATAL: Failed to install boto3. Cannot proceed with R2 upload.")
        sys.exit(1) # Exit if boto3 cannot be installed

    # 3. Write core scripts and systemd service file
    scripts_created_successfully = True
    if not write_file_if_missing(os.path.join(SCRIPTS_DIR, "tmate_script.py"), tmate_script_content):
        scripts_created_successfully = False
    if not write_file_if_missing(os.path.join(SCRIPTS_DIR, "upload_to_r2.py"), upload_to_r2_content):
        scripts_created_successfully = False
    if not write_file_if_missing(os.path.join(SCRIPTS_DIR, "tmate_loop.sh"), tmate_loop_content, executable=True):
        scripts_created_successfully = False
    if not write_file_if_missing(SERVICE_PATH, service_unit_content):
        scripts_created_successfully = False

    if not scripts_created_successfully:
        log("FATAL: One or more critical script files could not be created. Exiting.")
        sys.exit(1) # Exit if essential script creation fails

    # 4. Enable and start the systemd service
    enable_and_start_service()

    log("setup_tmate_access.py finished successfully.")
    log("--- End setup_tmate_access.py ---")