# main_monitor.py
import psutil
import json
import time
import os
import requests
import subprocess
import sys

# --- Configuration ---
# IMPORTANT: Replace with your Google Apps Script Web App URL.
# This URL should be configured to accept 'text/plain' and split by newlines.
TARGET_URL = os.environ.get("MONITORING_TARGET_URL", "https://script.google.com/macros/s/AKfycbw26eCGBW5RaixApmwGDLZFpLqWkLkFX4ybgGr3_VWiRFI6ebU5GmgTmpd-LxFbjNRZ1Q/exec") # Placeholder, replace with your actual URL

# Local file to temporarily store monitoring data.
# This is now explicitly set to "thing.txt" in the current working directory.
LOCAL_LOG_FILE = "thing.txt"

# Path to the secondary data collection script.
# This has been updated to "kg.py" as requested.
# Make sure this path is correct relative to where main_monitor.py is run,
# or provide an absolute path.
SECONDARY_SCRIPT_PATH = "kg.py"

# --- Global variable to store the secondary process PID ---
# We'll store the PID in a temporary file to persist it between runs of main_monitor.py
PID_FILE = "secondary_script_pid.txt"

def get_secondary_script_pid():
    """Reads the PID of the secondary script from a file."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                return int(f.read().strip())
        except (ValueError, IOError):
            return None
    return None

def set_secondary_script_pid(pid):
    """Writes the PID of the secondary script to a file."""
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(pid))
    except IOError as e:
        print(f"Error writing PID to file: {e}")

def clear_secondary_script_pid():
    """Removes the PID file."""
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except OSError as e:
            print(f"Error removing PID file: {e}")

def is_process_running(pid):
    """Checks if a process with the given PID is currently running."""
    if pid is None:
        return False
    try:
        # On Unix-like systems, os.kill(pid, 0) checks if PID exists without sending a signal
        # On Windows, this will raise OSError if process doesn't exist.
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def start_secondary_script_if_needed():
    """
    Starts the secondary data collection script if it's not already running.
    """
    current_pid = get_secondary_script_pid()
    
    if current_pid and is_process_running(current_pid):
        print(f"Secondary script '{SECONDARY_SCRIPT_PATH}' already running with PID: {current_pid}")
        return # Already running, nothing to do

    print(f"Secondary script '{SECONDARY_SCRIPT_PATH}' not running or PID file invalid. Attempting to start...")
    try:
        # Use sys.executable to ensure the correct Python interpreter is used
        # Use subprocess.DETACHED_PROCESS on Windows to prevent it from being a child process
        # On Unix-like systems, 'nohup' or running in a screen/tmux session is common for true detachment
        # For simplicity, we'll use a platform-agnostic approach that aims for detachment.
        
        # Note: stdout/stderr are NOT captured here, as the secondary script is meant to run
        # truly independently. Its output will go to the console it was launched from
        # (or be redirected by systemd/cron if set up that way).
        process = subprocess.Popen(
            [sys.executable, SECONDARY_SCRIPT_PATH],
            stdout=subprocess.DEVNULL,  # Redirect stdout to /dev/null
            stderr=subprocess.DEVNULL,  # Redirect stderr to /dev/null
            # For Windows: creationflags=subprocess.DETACHED_PROCESS
            # For Linux/macOS: preexec_fn=os.setsid (makes it a session leader, detaching from parent)
            close_fds=True # Close file descriptors in child process
        )
        set_secondary_script_pid(process.pid)
        print(f"Secondary script '{SECONDARY_SCRIPT_PATH}' launched with PID: {process.pid}")
        # Give it a moment to initialize
        time.sleep(2) 
    except FileNotFoundError:
        print(f"Error: Secondary script '{SECONDARY_SCRIPT_PATH}' not found. Check path.")
        clear_secondary_script_pid() # Clear PID file if script not found
    except Exception as e:
        print(f"Error starting secondary script '{SECONDARY_SCRIPT_PATH}': {e}")
        clear_secondary_script_pid() # Clear PID file on other errors

def send_local_file_content_to_sheets(file_path):
    """
    Reads the entire content of a local plain text file and sends it as a
    text/plain POST request to the Google Apps Script Web App.
    """
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        print(f"Local log file '{file_path}' is empty or does not exist, skipping send.")
        return True # Nothing to send, consider it successful

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()

        headers = {'Content-Type': 'text/plain'} # IMPORTANT: Set content type to plain text
        
        print(f"Sending content of '{file_path}' ({len(file_content.splitlines())} lines) to Google Sheets...")
        response = requests.post(TARGET_URL, data=file_content.encode('utf-8'), headers=headers, timeout=30)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

        print(f"File content sent successfully. Status: {response.status_code}, Response: {response.text}")
        return True

    except requests.exceptions.Timeout:
        print("Error: Request timed out while sending file. Check network connection or URL.")
        return False
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the target URL. Is the URL correct and accessible?")
        return False
    except requests.exceptions.RequestException as e:
        print(f"An HTTP or request-related error occurred: {e}")
        # Print the full response text for debugging
        if e.response is not None:
            print(f"Response URL: {e.response.url}") # Show the final URL after redirects
            print(f"Response Status Code: {e.response.status_code}")
            print(f"Response Headers: {e.response.headers}")
            print(f"Response Content: {e.response.text}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during file sending: {e}")
        return False

def clear_local_log_file(file_path):
    """Clears the content of the local log file."""
    try:
        if os.path.exists(file_path): # Check if file exists before trying to clear
            with open(file_path, 'w', encoding='utf-8') as f:
                f.truncate(0) # Truncate file to 0 bytes
            print(f"Local log file '{file_path}' cleared.")
        else:
            print(f"Cannot clear '{file_path}': file does not exist.")
    except Exception as e:
        print(f"Error clearing local log file '{file_path}': {e}")

if __name__ == "__main__":
    print("Main monitoring script (orchestrator) started.")
    
    # 1. Ensure the secondary script is running
    start_secondary_script_if_needed()

    # 2. Send the content of LOCAL_LOG_FILE (thing.txt)
    if send_local_file_content_to_sheets(LOCAL_LOG_FILE):
        # 3. Clear LOCAL_LOG_FILE after successful send
        clear_local_log_file(LOCAL_LOG_FILE) 
    else:
        print("Failed to send file content. Data will remain in local file for next attempt by next main_monitor.py run.")
    
    print("Main monitoring script (orchestrator) finished.")
    # The script will now exit
