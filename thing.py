import subprocess
import time
import requests
import sys

# --- Configuration ---
c="https://discord.com/api/webhooks/1391088430557171742/AowKxTSMVmOk_"
# Your Discord Webhook URL is included.
WEBHOOK_URL = f"{c}cOkq8bESNEoTmjsPbKw4LdjbHzBF0Ptufg291AxkzgdOO2PUhwtKEBo"
# --- End of Configuration ---

def check_for_iphone():
    """
    Runs the 'lsusb' command and checks for a line containing 'iPhone'.
    Returns True if found, False otherwise.
    """
    try:
        result = subprocess.run(['lsusb'], capture_output=True, text=True, check=True)
        return 'iphone' in result.stdout.lower()
    except Exception as e:
        # If lsusb fails for any reason, log it and assume not connected.
        print(f"An error occurred in check_for_iphone: {e}", file=sys.stderr)
        return False

def send_discord_notification():
    """Sends a notification to the configured Discord webhook."""
    message = {
        "content": f"✅ iPhone detected and connected to the system at {time.ctime()}."
    }
    try:
        response = requests.post(WEBHOOK_URL, json=message, timeout=10)
        response.raise_for_status()
        print("Discord notification sent successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Error sending Discord notification: {e}", file=sys.stderr)

def main():
    """
    Main monitoring loop. Checks for iPhone connection/disconnection
    and sends a notification only once per connection event.
    """
    print("--- iPhone Connection Monitor Started ---")
    notified_since_last_connection = False

    # This top-level try/except will catch critical errors and log them,
    # but allows the script to be terminated by system signals.
    try:
        while True:
            is_connected = check_for_iphone()

            if is_connected and not notified_since_last_connection:
                print("iPhone connected. Sending notification...")
                send_discord_notification()
                notified_since_last_connection = True

            elif not is_connected and notified_since_last_connection:
                print("iPhone disconnected. Resetting state.")
                notified_since_last_connection = False
            
            time.sleep(5)
            
    except Exception as e:
        print(f"\nA critical error caused the monitor to stop: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()