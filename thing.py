#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ==============================================================================
#  TAILSCALE RECOVERY SCRIPT (Enhanced with Extra Error Handling)
#
#  This script automatically fixes a broken Tailscale configuration and
#  saves a detailed execution log to /tmp/console.log
#
#  IT MUST BE RUN WITH ROOT PRIVILEGES (e.g., `sudo python3 this_script.py`)
# ==============================================================================

import os
import subprocess
import sys
import time
from datetime import datetime

# --- Configuration ---
CONFIG_FILE_PATH = "/etc/default/tailscaled"
CORRECT_LINE = 'FLAGS=""\n'
LOG_FILE_PATH = "/tmp/console.log"
SERVICE_NAME = "tailscaled.service"
RESTART_TIMEOUT_SECONDS = 60
POST_RESTART_WAIT_SECONDS = 15

def run_command(command):
    """A helper function to run shell commands with logging and timeouts."""
    print(f"Running command: {' '.join(command)}")
    try:
        # ENHANCEMENT: Added a timeout to prevent the script from hanging indefinitely.
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=RESTART_TIMEOUT_SECONDS
        )
        if result.stdout:
            print(f"Stdout: {result.stdout.strip()}")
        if result.stderr:
            print(f"Stderr: {result.stderr.strip()}")
        print("Command successful.")
        return True
    except FileNotFoundError:
        print(f"CRITICAL ERROR: Command not found: '{command[0]}'. Is the system PATH correct?")
        return False
    except subprocess.CalledProcessError as e:
        print(f"CRITICAL ERROR: Command failed with exit code {e.returncode}.")
        print(f"Stderr: {e.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired as e:
        print(f"CRITICAL ERROR: Command timed out after {RESTART_TIMEOUT_SECONDS} seconds.")
        print(f"Stderr on timeout: {e.stderr.strip() if e.stderr else 'N/A'}")
        return False

def check_service_status(initial_check=False):
    """Checks and logs the current status of the Tailscale service."""
    status_command = ["systemctl", "is-active", SERVICE_NAME]
    if initial_check:
        print(f"\n--- Performing initial status check for {SERVICE_NAME} ---")
    else:
        print(f"\n--- Performing post-restart verification for {SERVICE_NAME} ---")
    
    # This command returns exit code 0 if active, non-zero otherwise. `check=True` is not used here.
    result = subprocess.run(status_command, capture_output=True, text=True)
    status = result.stdout.strip()
    print(f"Service status is: '{status}'")
    return status == "active"

def fix_config_file():
    """Reads and reverts the configuration file."""
    print(f"\n--- Attempting to fix configuration file: {CONFIG_FILE_PATH} ---")
    # ENHANCEMENT: Using os.path.isfile for a more specific check.
    if not os.path.isfile(CONFIG_FILE_PATH):
        print(f"Warning: Config file not found at {CONFIG_FILE_PATH}.")
        return True # Return True to allow restart attempt regardless.

    try:
        with open(CONFIG_FILE_PATH, 'r') as f: lines = f.readlines()
        
        # Create a new list of lines with the modification
        new_lines = [CORRECT_LINE if line.lstrip().startswith("FLAGS=") else line for line in lines]
        was_modified = any(line.lstrip().startswith("FLAGS=") for line in lines)

        if was_modified:
            print(f"Found and corrected 'FLAGS=' line. Writing changes...")
            with open(CONFIG_FILE_PATH, 'w') as f: f.writelines(new_lines)
            print(f"Successfully wrote corrected configuration.")
        else:
            print("Did not find a 'FLAGS=' line to modify. File is unchanged.")
        return True
    except Exception as e:
        print(f"CRITICAL ERROR: Could not read/write the config file: {e}")
        return False

def restart_service():
    """Runs systemd commands to reload and restart the service."""
    print(f"\n--- Reloading systemd daemon and restarting {SERVICE_NAME} ---")
    if not run_command(["systemctl", "daemon-reload"]): return False
    if not run_command(["systemctl", "restart", SERVICE_NAME]): return False
    return True

if __name__ == "__main__":
    # Setup logging to a file
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    try:
        with open(LOG_FILE_PATH, 'a') as log_file:
            sys.stdout = log_file
            sys.stderr = log_file

            print(f"\n=========================================================")
            print(f" SCRIPT EXECUTION @ {datetime.now().isoformat()} ")
            print(f"=========================================================")

            if os.geteuid() != 0:
                print("Error: This script requires root privileges. Please run with 'sudo'.")
                sys.exit(1)

            # ENHANCEMENT: Check status before we do anything.
            check_service_status(initial_check=True)

            if not fix_config_file():
                raise Exception("Failed to fix config file. Aborting.")
            
            if not restart_service():
                raise Exception("Failed to restart service. Aborting.")

            # ENHANCEMENT: Wait and verify that the restart was actually successful.
            print(f"Waiting {POST_RESTART_WAIT_SECONDS} seconds for service to initialize...")
            time.sleep(POST_RESTART_WAIT_SECONDS)
            if check_service_status():
                print("\n--- SUCCESS: Recovery complete and service is active. ---")
                print("You should now be able to reconnect via Tailscale.")
            else:
                print("\n--- FAILURE: Service is still not active after restart. ---")
                print("Please check the system journal ('journalctl -u tailscaled') for errors after getting access.")

    except Exception as e:
        print(f"\nAN UNHANDLED CRITICAL ERROR OCCURRED: {e}")
        # Log the exception to the original console if possible
        print(f"CRITICAL SCRIPT ERROR: {e}", file=original_stderr)
    finally:
        # Crucial cleanup to restore normal output and close the log file
        if 'log_file' in locals() and not log_file.closed:
            log_file.close()
        sys.stdout = original_stdout
        sys.stderr = original_stderr