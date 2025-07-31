import subprocess
import time
import requests
import sys
import os
from pathlib import Path
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import shutil

# --- Configuration ---
# The local directory where the iPhone will be mounted.
MOUNT_POINT = Path("/var/local/user_scripts/iphone_mount")

# Cloudflare R2 Bucket Details
R2_BUCKET_NAME = "thing"

# 🚨 SECURITY WARNING: Hardcoding keys is not recommended.
# Your Cloudflare R2 credentials obfuscated as requested.
ac1 = 'fd5b99900fc2700f1f893f9'
ac2 = 'ee5d52c07'
ak1 = 'db8efca097d2506714901db0'
ak2 = '6ea81b97'
sk1 = '4a873df3ad2fdd9be894f779461fb2ab'
sk2 = '9def4202ea50afc42e9ecf029498d0fa'

ACCOUNT_ID = f"{ac1}{ac2}"
ACCESS_KEY = f"{ak1}{ak2}"
SECRET_KEY = f"{sk1}{sk2}"

# Your original Discord Webhook URL.
c="https://discord.com/api/webhooks/1391088430557171742/AowKxTSMVmOk_"
WEBHOOK_URL = f"{c}cOkq8bESNEoTmjsPbKw4LdjbHzBF0Ptufg291AxkzgdOO2PUhwtKEBo"
# --- End of Configuration ---

# This now connects to the Cloudflare R2 S3-compatible endpoint.
endpoint_url = f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com"
r2_client = boto3.client(
    's3',
    endpoint_url=endpoint_url,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    region_name="auto" # Required for Cloudflare R2
)

def send_discord_notification(message_content):
    """Sends a notification to the configured Discord webhook."""
    if not WEBHOOK_URL.startswith("https://discord.com/api/webhooks/"):
        return
    message = {"content": message_content}
    try:
        response = requests.post(WEBHOOK_URL, json=message, timeout=10)
        response.raise_for_status()
        print("Discord notification sent successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Error sending Discord notification: {e}", file=sys.stderr)

def check_for_iphone():
    """Runs 'lsusb' and checks for a line containing 'iPhone'."""
    try:
        result = subprocess.run(['lsusb'], capture_output=True, text=True, check=True)
        return 'iphone' in result.stdout.lower()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def is_tool_installed(name):
    """Check whether `name` is on PATH and marked as executable."""
    return shutil.which(name) is not None

def mount_iphone():
    """Creates mount point and mounts the iPhone using ifuse."""
    if not MOUNT_POINT.exists():
        print(f"Creating mount directory at: {MOUNT_POINT}")
        try:
            MOUNT_POINT.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            print(f"Fatal Error: Permission denied creating {MOUNT_POINT}.", file=sys.stderr)
            print("Please run the setup commands: 'sudo mkdir -p /var/local/user_scripts && sudo chown $USER:$USER /var/local/user_scripts'", file=sys.stderr)
            return False

    print("Attempting to mount iPhone...")
    try:
        subprocess.run(['fusermount', '-u', str(MOUNT_POINT)], check=False, capture_output=True)
        subprocess.run(['ifuse', str(MOUNT_POINT)], check=True, capture_output=True, text=True)
        print("✅ iPhone mounted successfully.")
        return True
    except FileNotFoundError:
        print("Error: 'ifuse' command not found. Please install it with 'sudo apt-get install ifuse'", file=sys.stderr)
        return False
    except subprocess.CalledProcessError as e:
        print(f"Error mounting iPhone: {e.stderr}", file=sys.stderr)
        print("Please ensure the iPhone is unlocked and you have 'trusted' this computer.", file=sys.stderr)
        return False

def unmount_iphone():
    """Unmounts the iPhone."""
    print("Unmounting iPhone...")
    try:
        subprocess.run(['fusermount', '-u', str(MOUNT_POINT)], check=True, capture_output=True)
        print("✅ Unmount successful.")
    except subprocess.CalledProcessError as e:
        print(f"Could not unmount: {e.stderr.strip()}. It might have already been disconnected.", file=sys.stderr)

def upload_files_to_r2():
    """Scans, sorts, and uploads files from the mount point to R2."""
    print(f"Starting scan of {MOUNT_POINT}...")
    try:
        all_files = [p for p in MOUNT_POINT.rglob('*') if p.is_file()]
        if not all_files:
            print("No files found on the device.")
            send_discord_notification("iPhone connected, but no files found to back up.")
            return

        all_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        total_files = len(all_files)
        send_discord_notification(f"iPhone connected. Found {total_files} files. Starting backup to R2 bucket `{R2_BUCKET_NAME}`...")
        print(f"Found {total_files} files. Checking against R2 and uploading new items...")

        uploaded_count = 0
        skipped_count = 0

        for i, local_path in enumerate(all_files):
            r2_object_key = str(local_path.relative_to(MOUNT_POINT))
            
            try:
                r2_client.head_object(Bucket=R2_BUCKET_NAME, Key=r2_object_key)
                skipped_count += 1
                continue
            except ClientError as e:
                if e.response['Error']['Code'] != '404':
                    print(f"Couldn't check '{r2_object_key}': {e}", file=sys.stderr)
                    continue

            print(f"[{skipped_count + uploaded_count + 1}/{total_files}] UPLOAD: '{r2_object_key}'")
            try:
                r2_client.upload_file(str(local_path), R2_BUCKET_NAME, r2_object_key)
                uploaded_count += 1
            except Exception as e:
                print(f"Failed to upload '{local_path}': {e}", file=sys.stderr)
        
        summary_msg = f"✅ Backup complete. Uploaded {uploaded_count} new files. Skipped {skipped_count} existing files."
        print(f"\n{summary_msg}\n")
        send_discord_notification(summary_msg)

    except NoCredentialsError:
        err_msg = "🚨 Backup failed: R2 credentials are not configured correctly in the script."
        print(err_msg, file=sys.stderr)
        send_discord_notification(err_msg)
    except Exception as e:
        err_msg = f"🚨 An error occurred during the upload process: {e}"
        print(f"\n{err_msg}", file=sys.stderr)
        send_discord_notification(err_msg)

def main():
    """Main monitoring loop."""
    if not is_tool_installed('ifuse'):
        print("Fatal Error: 'ifuse' is not installed. Please run 'sudo apt-get install ifuse'.", file=sys.stderr)
        sys.exit(1)
        
    print("--- iPhone R2 Backup Monitor Started ---")
    print(f"Using mount point: '{MOUNT_POINT}'")
    print(f"Backing up to R2 bucket: '{R2_BUCKET_NAME}'")
    
    upload_session_active = False

    while True:
        try:
            is_connected = check_for_iphone()

            if is_connected and not upload_session_active:
                upload_session_active = True
                print("\niPhone connected. Starting backup process...")
                time.sleep(2) 

                if mount_iphone():
                    try:
                        upload_files_to_r2()
                    finally:
                        unmount_iphone()
                else:
                    send_discord_notification("⚠️ iPhone connected, but failed to mount it.")

            elif not is_connected and upload_session_active:
                print("\niPhone disconnected. Resetting for next session.")
                upload_session_active = False
            
            time.sleep(10)
            
        except KeyboardInterrupt:
            print("\nMonitor stopped by user. Ensuring iPhone is unmounted...")
            unmount_iphone() 
            break
        except Exception as e:
            print(f"\nA critical error occurred in the main loop: {e}", file=sys.stderr)
            unmount_iphone() 
            time.sleep(30)

if __name__ == "__main__":
    main()