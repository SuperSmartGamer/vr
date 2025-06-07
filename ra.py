#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Automates the installation and configuration of Tailscale with SSH on a
Debian-based system like Zorin OS. This version enables Tailscale SSH
and relies on the authentication key to apply necessary tags (configured
in the Tailscale Admin Console) for broad access.

This script performs the following actions:
1. Verifies it is run with root privileges.
2. Checks for and installs Tailscale if it's missing.
3. Authenticates the device to a Tailscale network using a provided auth key.
4. Enables the Tailscale SSH server.

All terminal output (stdout and stderr) will also be saved to 'ssher.txt'
in the same directory as this script.
"""
import subprocess
import os
import sys
import json
import datetime
from typing import List, Optional
# Assuming upload_to_r2 is defined elsewhere or not critical for core functionality
# If you have an `upload.py` with `upload_to_r2`, uncomment the line below.
# from upload import upload_to_r2 

# --- CONFIGURATION ---
# IMPORTANT: Replace this with your actual Tailscale authentication key.
# For better security, consider using an environment variable instead:
#
# TAILSCALE_AUTH_KEY = os.environ.get("TS_AUTH_KEY")
# if not TAILSCALE_AUTH_KEY:
#     print("Error: TS_AUTH_KEY environment variable not set. Please set it or hardcode it.")
#     sys.exit(1)
k1,k2,k3="tskey-aut","h-k2sUqX9Xe621CNTRL-","XVZtjVekXXNa1pZrHRMgXNrnAJtbjnef"
key=f"{k1}{k2}{k3}"
TAILSCALE_AUTH_KEY =key

# --- END CONFIGURATION ---


class ScriptError(Exception):
    """Custom exception for script-related errors."""
    pass


class Tee:
    """
    A class to redirect stdout/stderr to both a file and the original stream.
    """
    def __init__(self, primary_stream, secondary_stream):
        self.primary_stream = primary_stream
        self.secondary_stream = secondary_stream

    def write(self, data):
        self.primary_stream.write(data)
        self.secondary_stream.write(data)

    def flush(self):
        self.primary_stream.flush()
        self.secondary_stream.flush()


def setup_logging():
    """
    Sets up logging to redirect stdout and stderr to 'ssher.txt'
    in the script's directory, while also printing to the console.
    """
    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(script_dir, "ssher.txt")

    try:
        # Open the log file in append mode ('a') for continuous logging
        # buffering=1 means line-buffered, which is good for real-time viewing
        log_file = open(log_file_path, "a", buffering=1, encoding='utf-8')
    except IOError as e:
        # If the log file cannot be opened, print an error and continue without file logging
        print(f"Error: Could not open log file '{log_file_path}' for writing: {e}", file=sys.stderr)
        return

    # Store original stdout and stderr to restore them later if needed (though not implemented here)
    # original_stdout = sys.stdout
    # original_stderr = sys.stderr

    # Create Tee objects to redirect output
    sys.stdout = Tee(sys.stdout, log_file)
    sys.stderr = Tee(sys.stderr, log_file)

    # Add a header to the log file for each run
    print(f"\n--- Log started at {datetime.datetime.now()} ---")
    print(f"All output for this run will be saved to: {log_file_path}")


def run_command(
    command: List[str], capture_output: bool = False
) -> Optional[str]:
    """
    Executes a shell command safely and returns its output.
    Logs the command being executed and its stdout/stderr.

    Args:
        command: The command and its arguments as a list of strings.
        capture_output: If True, returns the command's stdout.

    Returns:
        The command's stdout as a string if capture_output is True, else None.

    Raises:
        ScriptError: If the command returns a non-zero exit code.
    """
    # Print the command being executed for logging
    print(f"\n[COMMAND] Executing: {' '.join(command)}")
    try:
        process = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True, # Always capture output to log it
            encoding='utf-8'
        )
        if process.stdout:
            # Log standard output from the command
            print(f"[STDOUT]\n{process.stdout.strip()}")
        if process.stderr:
            # Log standard error from the command, even if successful
            print(f"[STDERR]\n{process.stderr.strip()}")
        if capture_output:
            return process.stdout.strip()
        return None
    except FileNotFoundError:
        error_msg = f"Error: Command not found: '{command[0]}'. Is it in the system's PATH?"
        print(f"❌ {error_msg}", file=sys.stderr) # Print to both console and log
        raise ScriptError(error_msg)
    except subprocess.CalledProcessError as e:
        error_message = (
            f"Command '{' '.join(command)}' failed with return code {e.returncode}.\n"
            f"STDOUT: {e.stdout.strip()}\n"
            f"STDERR: {e.stderr.strip()}"
        )
        print(f"❌ {error_message}", file=sys.stderr) # Print to both console and log
        raise ScriptError(error_message)


def is_package_installed(package_name: str) -> bool:
    """Checks if a Debian package is installed."""
    print(f"Checking if '{package_name}' is installed...")
    try:
        run_command(["dpkg-query", "-W", "-f=${Status}", package_name])
        print(f"'{package_name}' is installed.")
        return True
    except ScriptError:
        print(f"'{package_name}' is NOT installed.")
        return False


def get_ubuntu_codename() -> str:
    """Gets the Ubuntu release codename for the Tailscale repository."""
    print("Attempting to determine Ubuntu codename...")
    try:
        codename = run_command(["lsb_release", "-cs"], capture_output=True)
        print(f"Detected Ubuntu codename: '{codename}'.")
        return codename
    except ScriptError as e:
        print(f"Warning: Could not determine Ubuntu codename. Falling back to 'jammy'. Error: {e}")
        return "jammy"


def install_tailscale():
    """Installs Tailscale on the system if not already present."""
    if is_package_installed("tailscale"):
        print("✅ Tailscale is already installed.")
        return

    print("🔹 Tailscale not found. Starting installation...")
    try:
        # Check if gnupg is installed, and install if not
        print("Checking if 'gnupg' is installed...")
        if not is_package_installed("gnupg"):
            print("❗ 'gnupg' not found. Installing it now...")
            run_command(["apt-get", "update"]) # Ensure apt-get is up-to-date before installing gnupg
            run_command(["apt-get", "install", "-y", "gnupg"])
            print("✅ 'gnupg' installed successfully.")
        else:
            print("✅ 'gnupg' is already installed.")

        # Ensure /usr/share/keyrings exists
        print("Ensuring /usr/share/keyrings directory exists...")
        run_command(["mkdir", "-p", "--mode=0755", "/usr/share/keyrings"])

        print("Adding Tailscale's GPG key using gpg --dearmor...")
        # Use gpg --dearmor to properly handle the GPG key
        # We need to pipe the curl output to gpg --dearmor
        # Using subprocess.Popen for curl to manage its stdout as a pipe
        curl_process = subprocess.Popen(
            ["curl", "-fsSL", "https://pkgs.tailscale.com/stable/ubuntu/jammy.asc"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, # Capture stderr for curl for better error messages
            text=True,
            encoding='utf-8'
        )
        # Using subprocess.run for gpg to read from curl's stdout
        gpg_process = subprocess.run(
            ["gpg", "--dearmor", "-o", "/usr/share/keyrings/tailscale-archive-keyring.gpg"],
            stdin=curl_process.stdout,
            check=True,
            text=True,
            capture_output=True, # Capture output of gpg for logging
            encoding='utf-8'
        )
        # Close curl's stdout to prevent deadlocks and allow curl to exit cleanly
        curl_process.stdout.close() 
        # Wait for curl_process to finish, important for proper error handling of the pipe
        curl_process.wait()

        # Check curl's return code after it has finished
        if curl_process.returncode != 0:
            raise ScriptError(f"Curl failed with return code {curl_process.returncode}. STDERR: {curl_process.stderr.strip()}")

        if gpg_process.stdout:
            print(f"[STDOUT]\n{gpg_process.stdout.strip()}")
        if gpg_process.stderr:
            print(f"[STDERR]\n{gpg_process.stderr.strip()}")
        if gpg_process.returncode != 0:
            raise ScriptError(f"GPG key processing failed with return code {gpg_process.returncode}")
        print("Tailscale GPG key added successfully.")

        print("Adding Tailscale repository...")
        codename = get_ubuntu_codename()
        # The content of the sources.list.d file
        repo_list_content = (
            f"deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] "
            f"https://pkgs.tailscale.com/stable/ubuntu {codename} main"
        )
        # Use tee with subprocess to write to the file as root, which is more robust
        # than direct file open in Python when dealing with permissions.
        p = subprocess.run(
            ["tee", "/etc/apt/sources.list.d/tailscale.list"],
            input=repo_list_content.encode('utf-8'), # Input must be bytes
            check=True,
            text=True,
            capture_output=True,
            encoding='utf-8'
        )
        if p.stdout:
            print(f"[STDOUT]\n{p.stdout.strip()}")
        if p.stderr:
            print(f"[STDERR]\n{p.stderr.strip()}")

        print("Tailscale repository added.")

        # Update package lists and install
        print("Updating package lists...")
        run_command(["apt-get", "update"])
        print("Installing Tailscale package...")
        run_command(["apt-get", "install", "-y", "tailscale"])
        print("✅ Tailscale installed successfully.")
    except (ScriptError, IOError, subprocess.CalledProcessError) as e:
        print(f"❌ Installation failed: {e}", file=sys.stderr)
        sys.exit(1)


def setup_tailscale(auth_key: str):
    """
    Ensures the Tailscale service is running and authenticates the node
    with SSH enabled.
    """
    print("🔹 Configuring Tailscale service...")
    try:
        run_command(["systemctl", "enable", "--now", "tailscaled"])
        print("Tailscale daemon enabled and started.")
    except ScriptError as e:
        print(f"❌ Failed to start or enable tailscaled service: {e}", file=sys.stderr)
        sys.exit(1)

    # Check if already authenticated and running using reliable JSON output
    try:
        print("Checking Tailscale status...")
        status_json = run_command(["tailscale", "status", "--json"], capture_output=True)
        status = json.loads(status_json)
        if status.get("BackendState") == "Running" and status.get("Self", {}).get("Online"):
            print("✅ Tailscale is already authenticated and running.")
            return
    except (ScriptError, json.JSONDecodeError) as e:
        # This can happen if tailscaled is not fully up yet or status is not valid JSON. Continue to auth.
        print(f"Could not parse Tailscale status (this is normal on first run or if not online yet). Error: {e}")

    print("Authenticating with Tailscale and enabling SSH...")
    try:
        # The --ssh flag is the correct, modern way to enable SSH on auth.
        auth_command = [
            "tailscale", "up",
            f"--authkey={auth_key}",
            "--ssh",
            "--accept-routes", # Often useful to accept routes from the tailnet
            "--accept-dns",    # Often useful to accept DNS settings from the tailnet
            # NO --tag ARGUMENT HERE. Tags are specified on the authkey itself.
        ]
        run_command(auth_command)
        print("✅ Tailscale authenticated successfully and SSH is enabled.")
    except ScriptError as e:
        print(f"❌ Tailscale authentication and configuration failed: {e}", file=sys.stderr)
        print("\nPlease check that your auth key is valid and has not expired, and that its associated tags are correctly configured in the Tailscale Admin Console.", file=sys.stderr)
        sys.exit(1)


def main():
    """Main execution function."""
    setup_logging() # Call this first to start logging immediately

    if os.geteuid() != 0:
        print("❌ This script must be run as root. Please use 'sudo'.", file=sys.stderr)
        sys.exit(1)

    print("--- Starting Tailscale SSH Setup (Max Flexibility/Min Security) ---")

    install_tailscale()
    setup_tailscale(TAILSCALE_AUTH_KEY)

    print("\n--- ✅ Remote Access Setup Complete ---")
    print("This machine is now part of your Tailscale network with SSH enabled.")
    print("\n❗ IMPORTANT: To grant broad SSH access, you MUST:")
    print("1. Configure your Tailscale Authentication Key (used in this script) to apply the 'ssh-enabled-device' tag.")
    print("   Go to: https://login.tailscale.com/admin/settings/authkeys")
    print("   Edit the reusable key, set 'Ephemeral' to OFF, and add 'ssh-enabled-device' to 'Tags'.")
    print("2. Configure your Tailscale ACLs to allow access to devices with this tag.")
    print("   Go to: https://login.tailscale.com/admin/acls")
    print("   Replace your entire ACL JSON with the 'Maximum Flexibility ACL' provided below.")
    print("\nTo connect from another machine in your tailnet (after updating ACLs):")
    try:
        hostname = run_command(['hostname'], capture_output=True)
        print(f"ssh <any_local_username>@{hostname}") # Use hostname for easier remembrance
        print(f"(e.g., ssh root@{hostname} or ssh your_linux_username@{hostname})")
        print(f"(or ssh <any_local_username>@<TAILSCALE_IP_OF_THIS_MACHINE>)")
    except ScriptError:
        print("ssh <any_local_username>@<TAILSCALE_IP_OF_THIS_MACHINE>")
    print("\nRemember that 'any_local_username' must be an actual user account on the destination Linux machine.")
    # If `upload_to_r2` function is intended to be used, ensure it's defined
    # or remove this call if it's not applicable.
    # upload_to_r2(f"ssher.txt") 

if __name__ == "__main__":
    main()