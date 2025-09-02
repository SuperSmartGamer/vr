#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Automates the installation and configuration of Tailscale with SSH on a
Debian-based system like Zorin OS. This version enables Tailscale SSH
and relies on the authentication key to apply necessary tags (configured
in the Tailscale Admin Console) for broad access.

This script performs the following actions:
1. Verifies it is run with root privileges.
2. Checks for and installs Tailscale if it's missing using the official Tailscale install script.
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

# Assuming upload_to_r2 is defined elsewhere or not critical for core functionality.
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
k1,k2,k3="tskey-auth-","kRJi1zCxHu11CNTRL-","xEFwxoPBvtQFVSnCk6cmtQ6heCctNZpqH"

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

    def flush(self, *args, **kwargs):
        self.primary_stream.flush(*args, **kwargs)
        self.secondary_stream.flush(*args, **kwargs)


def setup_logging():
    """
    Sets up logging to redirect stdout and stderr to 'ssher.txt'
    in the script's directory, while also printing to the console.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(script_dir, "ssher.txt")

    try:
        log_file = open(log_file_path, "a", buffering=1, encoding='utf-8')
    except IOError as e:
        print(f"Error: Could not open log file '{log_file_path}' for writing: {e}", file=sys.stderr)
        return

    sys.stdout = Tee(sys.stdout, log_file)
    sys.stderr = Tee(sys.stderr, log_file)

    print(f"\n--- Log started at {datetime.datetime.now()} ---")
    print(f"All output for this run will be saved to: {log_file_path}")


def run_command(
    command: List[str] or str, capture_output: bool = False, shell: bool = False
) -> Optional[str]:
    """
    Executes a shell command safely and returns its output.
    Logs the command being executed and its stdout/stderr.

    Args:
        command: The command and its arguments as a list of strings (preferred)
                 or a string if shell=True.
        capture_output: If True, returns the command's stdout.
        shell: If True, executes the command through the shell.

    Returns:
        The command's stdout as a string if capture_output is True, else None.

    Raises:
        ScriptError: If the command returns a non-zero exit code.
    """
    cmd_display = command if isinstance(command, str) else ' '.join(command)
    print(f"\n[COMMAND] Executing: {cmd_display}")
    try:
        process = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True, # Always capture output to log it
            encoding='utf-8',
            shell=shell
        )
        if process.stdout:
            print(f"[STDOUT]\n{process.stdout.strip()}")
        if process.stderr:
            print(f"[STDERR]\n{process.stderr.strip()}")
        if capture_output:
            return process.stdout.strip()
        return None
    except FileNotFoundError:
        error_msg = f"Error: Command not found: '{command[0] if isinstance(command, list) else command}'. Is it in the system's PATH?"
        print(f"❌ {error_msg}", file=sys.stderr)
        raise ScriptError(error_msg)
    except subprocess.CalledProcessError as e:
        error_message = (
            f"Command '{cmd_display}' failed with return code {e.returncode}.\n"
            f"STDOUT: {e.stdout.strip()}\n"
            f"STDERR: {e.stderr.strip()}"
        )
        print(f"❌ {error_message}", file=sys.stderr)
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


def install_tailscale():
    """Installs Tailscale on the system using the official one-liner script."""
    if is_package_installed("tailscale"):
        print("✅ Tailscale is already installed.")
        return

    print("🔹 Tailscale not found. Starting installation using official script...")
    try:
        # The official Tailscale installation one-liner
        install_command = "curl -fsSL https://tailscale.com/install.sh | sh"
        
        print("Executing Tailscale's official installation script...")
        run_command(install_command, shell=True) # Use shell=True for the pipe
        
        print("✅ Tailscale installed successfully via official script.")
    except ScriptError as e:
        print(f"❌ Tailscale installation failed: {e}", file=sys.stderr)
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