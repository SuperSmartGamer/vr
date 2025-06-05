#!/usr/bin/env python3
import os
import subprocess
import stat
import traceback
import time
import sys
import shutil # Import shutil for file copying

# --- Configuration ---
MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(MAIN_DIR, "scripts")
LOG_FILE = os.path.join(MAIN_DIR, "console.log") # Main log file for all script output
SERVICE_PATH = "/etc/systemd/system/tmate-persistent.service" # Systemd service unit file

# Cloudflare R2 Credentials (IMPORTANT: REPLACE WITH YOUR ACTUAL R2 API TOKEN)
R2_ACCESS_KEY = 'db8efca097d2506714901db06ea81b97' # Your R2 Access Key ID
R2_SECRET_KEY = '4a873df3ad2fdd9be894f77961fb2ab9def4202ea50afc42e9ecf029498d0fa' # Your R2 Secret Access Key
R2_ACCOUNT_ID = 'fd5b99900fc2700f1f893f9ee5d52c07' # Your Cloudflare Account ID (found in R2 endpoint URL)
R2_BUCKET_NAME = 'my-bucket' # Replace with your R2 bucket name
R2_ENDPOINT_URL = f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
R2_UPLOAD_KEY = 'tmate.txt' # The name of the file to be uploaded to your R2 bucket

# Local copy path
LOCAL_TMATE_COPY_PATH = os.path.join(MAIN_DIR, "tmate_connection_local.txt")


# --- Logging Helper ---
def log(message, level="INFO"):
    """Appends a timestamped message to the main log file (console.log)."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{timestamp}] [{level}] {message}"
    try:
        with open(LOG_FILE, "a") as log_f:
            log_f.write(f"{full_message}\n")
    except Exception:
        # Fallback to stderr if logging to file fails (shouldn't happen with root)
        print(f"FATAL: Could not write to log file. {full_message}", file=sys.stderr)

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
        log(f"Error creating {path}:\n{traceback.format_exc()}", level="ERROR")
        return False

# --- Dependency Installation ---
def install_apt_packages(packages):
    """Installs specified apt packages. Returns True on success, False on failure."""
    log(f"Attempting to install apt packages: {', '.join(packages)}...")
    try:
        log("Running apt update...")
        # Use a timeout for apt update to prevent hanging
        result = subprocess.run(["apt", "update"], check=True, capture_output=True, text=True, timeout=300)
        log(f"apt update STDOUT:\n{result.stdout.strip()}", level="DEBUG")
        if result.stderr: log(f"apt update STDERR:\n{result.stderr.strip()}", level="WARN")

        log("Running apt install...")
        result = subprocess.run(["apt", "install", "-y"] + packages, check=True, capture_output=True, text=True, timeout=300)
        log(f"apt install STDOUT:\n{result.stdout.strip()}", level="DEBUG")
        if result.stderr: log(f"apt install STDERR:\n{result.stderr.strip()}", level="WARN")

        log(f"Packages {', '.join(packages)} installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        log(f"Error during apt install of {', '.join(packages)}: Command failed with exit code {e.returncode}", level="ERROR")
        log(f"STDOUT:\n{e.stdout.strip()}", level="ERROR")
        log(f"STDERR:\n{e.stderr.strip()}", level="ERROR")
        return False
    except subprocess.TimeoutExpired:
        log(f"apt command timed out while installing {', '.join(packages)}.", level="ERROR")
        return False
    except Exception as e:
        log(f"An unexpected error occurred during apt install: {e}\n{traceback.format_exc()}", level="ERROR")
        return False

def install_python_package(package_name):
    """Installs a Python package using pip. Returns True on success, False on failure."""
    log(f"Attempting to install Python package '{package_name}'...")
    try:
        # Try to install pip if it's missing
        try:
            result = subprocess.run(["python3", "-m", "pip", "--version"], check=True, capture_output=True, text=True)
            log(f"pip check STDOUT:\n{result.stdout.strip()}", level="DEBUG")
            if result.stderr: log(f"pip check STDERR:\n{result.stderr.strip()}", level="WARN")
        except subprocess.CalledProcessError:
            log("pip not found for python3. Attempting to install python3-pip...", level="WARN")
            if not install_apt_packages(["python3-pip"]):
                log("Failed to install python3-pip. Cannot install Python packages.", level="ERROR")
                return False

        result = subprocess.run(["python3", "-m", "pip", "install", package_name], check=True, capture_output=True, text=True)
        log(f"pip install STDOUT:\n{result.stdout.strip()}", level="DEBUG")
        if result.stderr: log(f"pip install STDERR:\n{result.stderr.strip()}", level="WARN")

        log(f"Python package '{package_name}' installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        log(f"Error installing Python package '{package_name}': Command failed with exit code {e.returncode}", level="ERROR")
        log(f"STDOUT:\n{e.stdout.strip()}", level="ERROR")
        log(f"STDERR:\n{e.stderr.strip()}", level="ERROR")
        return False
    except Exception as e:
        log(f"An unexpected error occurred during Python package install: {e}\n{traceback.format_exc()}", level="ERROR")
        return False

# --- Systemd Service Management ---
def enable_and_start_service():
    """Reloads systemd daemon, enables, and starts the tmate-persistent service."""
    log("Attempting to enable and start tmate-persistent service.")
    try:
        result = subprocess.run(["systemctl", "daemon-reload"], check=True, capture_output=True, text=True)
        log(f"systemctl daemon-reload STDOUT:\n{result.stdout.strip()}", level="DEBUG")
        if result.stderr: log(f"systemctl daemon-reload STDERR:\n{result.stderr.strip()}", level="WARN")
        log("Systemd daemon reloaded.")
    except Exception:
        log(f"Error reloading systemd:\n{traceback.format_exc()}", level="ERROR")
        return

    if not os.path.exists(SERVICE_PATH):
        log(f"Service file {SERVICE_PATH} missing; cannot enable/start service.", level="ERROR")
        return

    try:
        result = subprocess.run(["systemctl", "enable", "tmate-persistent"], check=True, capture_output=True, text=True)
        log(f"systemctl enable STDOUT:\n{result.stdout.strip()}", level="DEBUG")
        if result.stderr: log(f"systemctl enable STDERR:\n{result.stderr.strip()}", level="WARN")
        log("Service 'tmate-persistent' enabled.")
    except subprocess.CalledProcessError: # Service may already be enabled
        log("Service 'tmate-persistent' may already be enabled (non-critical).", level="WARN")
    except Exception:
        log(f"Error enabling service:\n{traceback.format_exc()}", level="ERROR")

    try:
        result = subprocess.run(["systemctl", "is-active", "--quiet", "tmate-persistent"], check=True, capture_output=True, text=True)
        log(f"systemctl is-active STDOUT:\n{result.stdout.strip()}", level="DEBUG")
        if result.stderr: log(f"systemctl is-active STDERR:\n{result.stderr.strip()}", level="WARN")
        log("Service 'tmate-persistent' is already running.")
    except subprocess.CalledProcessError: # Service is not active
        try:
            result = subprocess.run(["systemctl", "start", "tmate-persistent"], check=True, capture_output=True, text=True)
            log(f"systemctl start STDOUT:\n{result.stdout.strip()}", level="DEBUG")
            if result.stderr: log(f"systemctl start STDERR:\n{result.stderr.strip()}", level="WARN")
            log("Started service 'tmate-persistent'.")
        except Exception:
            log(f"Error starting service:\n{traceback.format_exc()}", level="ERROR")
    except Exception: # General error checking status
        log(f"Error checking service status:\n{traceback.format_exc()}", level="ERROR")

# === Script Templates (Embedded within setup_tmate_access.py) ===

# 1. tmate_script.py: Installs tmate and extracts the SSH connection string.
tmate_script_content = f"""#!/usr/bin/env python3
import os
import subprocess
import traceback
import sys
import time

log_path = "{LOG_FILE}"
def log_local(msg, level="INFO"):
    try:
        with open(log_path, "a") as log_f:
            # Use triple curly braces for literal braces in the f-string within the embedded script
            log_f.write(f"[{{{{time.strftime('%Y-%m-%d %H:%M:%S')}}}}] [tmate_script] [{{{{level}}}}] {{{{msg}}}}\\n")
    except:
        pass

def run_command_and_log(cmd, description, check=True, timeout=None):
    # This line has the fix: 'description' is now correctly interpolated
    log_local(f"Executing: {{' '.join(cmd)}} ({{description}})")
    try:
        result = subprocess.run(cmd, check=check, capture_output=True, text=True, timeout=timeout)
        log_local(f"{{description}} STDOUT:\\n{{result.stdout.strip()}}", level="DEBUG")
        if result.stderr: log_local(f"{{description}} STDERR:\\n{{result.stderr.strip()}}", level="WARN")
        return result
    except subprocess.CalledProcessError as e:
        log_local(f"Error during {{description}}: Command failed with exit code {{e.returncode}}", level="ERROR")
        log_local(f"STDOUT:\\n{{e.stdout.strip()}}", level="ERROR")
        log_local(f"STDERR:\\n{{e.stderr.strip()}}", level="ERROR")
        raise # Re-raise to be caught by outer try-except
    except subprocess.TimeoutExpired:
        log_local(f"{{description}} command timed out.", level="ERROR")
        raise
    except FileNotFoundError:
        log_local(f"Error: Command not found for {{description}}.", level="ERROR")
        raise
    except Exception as e:
        log_local(f"An unexpected error occurred during {{description}}: {{e}}\\n{{traceback.format_exc()}}", level="ERROR")
        raise

def install_tmate():
    log_local("Attempting to install tmate...")
    try:
        run_command_and_log(["apt", "update"], "apt update", timeout=300)
        run_command_and_log(["apt", "install", "-y", "tmate"], "apt install tmate", timeout=300)
        log_local("tmate installed successfully.")
        return True
    except Exception:
        log_local("tmate installation failed.", level="ERROR")
        return False

try:
    # Check if tmate is already installed. `/usr/bin/tmate` is a common path.
    if not os.path.exists("/usr/bin/tmate"):
        log_local("tmate not found. Attempting installation.")
        if not install_tmate():
            log_local("tmate installation failed. Exiting tmate_script.", level="ERROR")
            sys.exit(1)
    else:
        log_local("tmate already installed.")

    log_local("Starting new tmate session in foreground to get SSH string...")
    # Start new session in foreground (remove -S and -d as they seem unrecognized)
    # This command will block until 'tmate-ready'
    run_command_and_log(["tmate", "new-session"], "tmate new session", timeout=120)
    log_local("tmate new session started and is ready.")

    log_local("Extracting tmate SSH connection string...")
    # Display the SSH connection string without using a specific socket for now
    # We assume 'tmate display' can find the current session.
    result = run_command_and_log(["tmate", "display", "-p", "#{{tmate_ssh}}"], "tmate display ssh string", timeout=30)

    ssh_connection_string = result.stdout.strip()
    if ssh_connection_string:
        with open('/tmp/tmate.txt', 'w') as f:
            f.write(ssh_connection_string)
        log_local(f"tmate SSH connection string saved to /tmp/tmate.txt: {{ssh_connection_string}}")
    else:
        log_local("Failed to extract tmate SSH connection string (output was empty).", level="ERROR")
        sys.exit(1) # Indicate failure if no string was extracted

    log_local("Killing tmate session as string extracted. Systemd will handle persistence.")
    # Kill the tmate session that was started in the foreground.
    # The systemd service will start its own persistent one.
    run_command_and_log(["tmate", "kill-session"], "tmate kill session", check=False) # check=False because it might fail if no session is found, but that's okay

except Exception as e:
    log_local(f"General error in tmate_script.py: {{e}}\\n{{traceback.format_exc()}}", level="ERROR")
    sys.exit(1) # Indicate failure
sys.exit(0) # Ensure script exits cleanly on success
"""

# 2. upload_to_r2.py: Uploads the tmate connection string to Cloudflare R2 and keeps a local copy.
upload_to_r2_content = f"""#!/usr/bin/env python3
import boto3
import traceback
import sys
import os
import time
import shutil # Import shutil for file copy

log_path = "{LOG_FILE}"
def log_local(msg, level="INFO"):
    try:
        with open(log_path, "a") as log_f:
            log_f.write(f"[{{{{time.strftime('%Y-%m-%d %H:%M:%S')}}}}] [upload_to_r2] [{{{{level}}}}] {{{{msg}}}}\\n")
    except:
        pass

ACCESS_KEY = '{R2_ACCESS_KEY}'
SECRET_KEY = '{R2_SECRET_KEY}'
ACCOUNT_ID = '{R2_ACCOUNT_ID}'
BUCKET_NAME = '{R2_BUCKET_NAME}'
endpoint_url = '{R2_ENDPOINT_URL}'
UPLOAD_KEY = '{R2_UPLOAD_KEY}'
TMATE_FILE = '/tmp/tmate.txt'
LOCAL_COPY_PATH = '{LOCAL_TMATE_COPY_PATH}' # Path for the local copy

try:
    if not os.path.exists(TMATE_FILE):
        log_local(f"Error: {{TMATE_FILE}} not found. Cannot upload or copy.", level="ERROR")
        sys.exit(1) # Indicate failure

    # --- Upload to R2 ---
    log_local("Initializing boto3 client for R2.")
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
    )

    log_local(f"Attempting to upload {{TMATE_FILE}} to R2 bucket {{BUCKET_NAME}} as {{UPLOAD_KEY}}...")
    s3.upload_fileobj(open(TMATE_FILE, 'rb'), BUCKET_NAME, UPLOAD_KEY)
    log_local("R2 upload successful.")

    # --- Keep local copy ---
    log_local(f"Attempting to copy {{TMATE_FILE}} to local path {{LOCAL_COPY_PATH}}...")
    shutil.copyfile(TMATE_FILE, LOCAL_COPY_PATH)
    log_local(f"Local copy of {{TMATE_FILE}} saved to {{LOCAL_COPY_PATH}}.")

except Exception as e:
    log_local(f"Error in upload_to_r2.py: {{e}}\\n{{traceback.format_exc()}}", level="ERROR")
    sys.exit(1) # Indicate failure
sys.exit(0) # Ensure script exits cleanly on success
"""

# 3. tmate_loop.sh: A bash script that continuously monitors tmate and orchestrates Python scripts.
tmate_loop_content = f"""#!/bin/bash
LOG_FILE="{LOG_FILE}"
TMATE_SOCKET="/tmp/tmate.sock" # Note: tmate might not use this socket if started without -S
TMATE_SCRIPT_PY="{os.path.join(SCRIPTS_DIR, 'tmate_script.py')}"
UPLOAD_R2_PY="{os.path.join(SCRIPTS_DIR, 'upload_to_r2.py')}"

echo "$(date) - [tmate_loop.sh] INFO - Script started." >> "$LOG_FILE"

while true; do
  # Check if a tmate process is actually running using pgrep.
  # We cannot reliably check for a socket if tmate is running without -S.
  # The Systemd service runs 'tmate -d', so we need to check for that.
  if ! pgrep -f "tmate -d" > /dev/null; then
    echo "$(date) - [tmate_loop.sh] INFO - Tmate detached session not found. Attempting to start new session and upload." >> "$LOG_FILE"
    
    # Run the Python script to create the tmate session and extract the string
    # This tmate session is temporary, just for getting the string.
    python3 "$TMATE_SCRIPT_PY"
    TMATE_STATUS=$?
    if [ $TMATE_STATUS -ne 0 ]; then
      echo "$(date) - [tmate_loop.sh] ERROR - tmate_script.py failed with exit code $TMATE_STATUS. Retrying in 1 second." >> "$LOG_FILE"
      sleep 1 # Check every second
      continue
    fi

    # Only attempt to upload if tmate_script.py succeeded
    python3 "$UPLOAD_R2_PY"
    UPLOAD_STATUS=$?
    if [ $UPLOAD_STATUS -ne 0 ]; then
      echo "$(date) - [tmate_loop.sh] ERROR - upload_to_r2.py failed with exit code $UPLOAD_STATUS. Retrying in 1 second." >> "$LOG_FILE"
      sleep 1 # Check every second
      continue
    fi
    echo "$(date) - [tmate_loop.sh] INFO - New tmate session (for string extraction) established and string uploaded." >> "$LOG_FILE"
  else
    echo "$(date) - [tmate_loop.sh] INFO - Tmate detached session appears active." >> "$LOG_FILE"
  fi
  
  sleep 1 # Check every second
done
"""

# 4. systemd service unit: Defines the systemd service for persistence.
# This service will start tmate in detached mode using its default socket.
service_unit_content = f"""[Unit]
Description=Persistent tmate session and R2 upload
After=network.target

[Service]
ExecStart=/usr/bin/tmate -d # Start tmate directly in detached mode
Restart=always
RestartSec=10s # Wait 10 seconds before restarting if it exits
User=root # Run as root to ensure full access and tmate installation/socket creation
StandardOutput=append:{LOG_FILE} # Append stdout of the bash script to log file
StandardError=append:{LOG_FILE} # Append stderr of the bash script to log file

[Install]
WantedBy=multi-user.target # Start when the system reaches multi-user runlevel
"""

# === Main Execution Logic ===
if __name__ == "__main__":
    log("--- Starting setup_tmate_access.py ---", level="INFO")

    # 1. Ensure necessary directories exist
    try:
        os.makedirs(SCRIPTS_DIR, exist_ok=True)
        log(f"Ensured directory {SCRIPTS_DIR} exists.", level="INFO")
    except Exception as e:
        log(f"FATAL: Error creating scripts directory {SCRIPTS_DIR}: {e}\n{traceback.format_exc()}", level="FATAL")
        sys.exit(1) # Exit if essential directory creation fails

    # 2. Install Python dependencies (boto3 and pip if needed)
    if not install_python_package("boto3"):
        log("FATAL: Failed to install boto3. Cannot proceed with R2 upload.", level="FATAL")
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
        log("FATAL: One or more critical script files could not be created. Exiting.", level="FATAL")
        sys.exit(1) # Exit if essential script creation fails

    # 4. Enable and start the systemd service
    enable_and_start_service()

    log("setup_tmate_access.py finished successfully.", level="INFO")
    log("--- End setup_tmate_access.py ---", level="INFO")