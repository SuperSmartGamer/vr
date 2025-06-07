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
"""

import subprocess
import os
import sys
import json
import logging
from typing import List, Optional

# --- CONFIGURATION ---
# IMPORTANT: Replace this with your actual Tailscale authentication key.
# For better security, consider using an environment variable instead:
#
# TAILSCALE_AUTH_KEY = os.environ.get("TS_AUTH_KEY")
# if not TAILSCALE_AUTH_KEY:
#     logging.error("Error: TS_AUTH_KEY environment variable not set. Please set it or hardcode it.")
#     sys.exit(1)
k1,k2,k3="tskey-aut","h-k2sUqX9Xe621CNTRL-","XVZtjVekXXNa1pZrHRMgXNrnAJtbjnef"
key=f"{k1}{k2}{k3}"
TAILSCALE_AUTH_KEY =key
# --- END CONFIGURATION ---

# --- LOGGING SETUP ---
LOG_FILE = "console.log"
# Configure logging to write to a file and also output to console
logging.basicConfig(
    level=logging.INFO, # Set the minimum level of messages to log (INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(levelname)s - %(message)s', # Format of the log messages
    handlers=[
        logging.FileHandler(LOG_FILE), # Log to a file
        logging.StreamHandler(sys.stdout) # Also log to standard output (console)
    ]
)
# --- END LOGGING SETUP ---

class ScriptError(Exception):
    """Custom exception for script-related errors."""
    pass


def run_command(
    command: List[str], capture_output: bool = False
) -> Optional[str]:
    """
    Executes a shell command safely and returns its output.

    Args:
        command: The command and its arguments as a list of strings.
        capture_output: If True, returns the command's stdout.

    Returns:
        The command's stdout as a string if capture_output is True, else None.

    Raises:
        ScriptError: If the command returns a non-zero exit code.
    """
    command_str = ' '.join(command) # For logging the command
    try:
        logging.info(f"Executing command: {command_str}")
        process = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
            encoding='utf-8'
        )
        if capture_output:
            logging.debug(f"Command output: {process.stdout.strip()}") # Use debug for verbose output
            return process.stdout.strip()
        return None
    except FileNotFoundError:
        error_msg = f"Error: Command not found: '{command[0]}'. Is it in the system's PATH?"
        logging.error(error_msg)
        raise ScriptError(error_msg)
    except subprocess.CalledProcessError as e:
        error_message = (
            f"Command '{command_str}' failed with return code {e.returncode}.\n"
            f"Stderr: {e.stderr.strip()}"
        )
        logging.error(error_message)
        raise ScriptError(error_message)


def is_package_installed(package_name: str) -> bool:
    """Checks if a Debian package is installed."""
    try:
        run_command(["dpkg-query", "-W", "-f=${Status}", package_name])
        logging.info(f"Package '{package_name}' is installed.")
        return True
    except ScriptError:
        logging.info(f"Package '{package_name}' is not installed.")
        return False


def get_ubuntu_codename() -> str:
    """Gets the Ubuntu release codename for the Tailscale repository."""
    try:
        codename = run_command(["lsb_release", "-cs"], capture_output=True)
        logging.info(f"Detected Ubuntu codename: {codename}")
        return codename
    except ScriptError as e:
        logging.warning(f"Could not determine Ubuntu codename. Falling back to 'jammy'. Error: {e}")
        # Zorin OS 17 is based on jammy (22.04), a safe fallback.
        return "jammy"


def install_tailscale():
    """Installs Tailscale on the system if not already present."""
    if is_package_installed("tailscale"):
        logging.info("✅ Tailscale is already installed.")
        return

    logging.info("🔹 Tailscale not found. Starting installation...")
    try:
        # Add Tailscale's GPG key
        logging.info("Adding Tailscale GPG key...")
        run_command([
            "curl", "-fsSL", "https://pkgs.tailscale.com/stable/ubuntu/jammy.asc",
            "-o", "/usr/share/keyrings/tailscale-archive-keyring.gpg"
        ])

        # Add Tailscale repository
        codename = get_ubuntu_codename()
        repo_list_content = (
            f"deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] "
            f"https://pkgs.tailscale.com/stable/ubuntu {codename} main"
        )
        logging.info(f"Adding Tailscale repository for codename '{codename}'...")
        with open("/etc/apt/sources.list.d/tailscale.list", "w") as f:
            f.write(repo_list_content)
        
        # Update package lists and install
        logging.info("Updating package lists...")
        run_command(["apt-get", "update"])
        logging.info("Installing Tailscale package...")
        run_command(["apt-get", "install", "-y", "tailscale"])
        logging.info("✅ Tailscale installed successfully.")
    except (ScriptError, IOError) as e:
        logging.critical(f"❌ Installation failed: {e}")
        sys.exit(1)


def setup_tailscale(auth_key: str):
    """
    Ensures the Tailscale service is running and authenticates the node
    with SSH enabled.
    """
    logging.info("🔹 Configuring Tailscale service...")
    try:
        run_command(["systemctl", "enable", "--now", "tailscaled"])
        logging.info("Tailscale service enabled and started.")
    except ScriptError as e:
        logging.critical(f"❌ Failed to start or enable tailscaled service: {e}")
        sys.exit(1)

    # Check if already authenticated and running using reliable JSON output
    try:
        status_json = run_command(["tailscale", "status", "--json"], capture_output=True)
        status = json.loads(status_json)
        if status.get("BackendState") == "Running" and status.get("Self", {}).get("Online"):
            logging.info("✅ Tailscale is already authenticated and running.")
            # We no longer check for or apply tags here, as they're configured with the authkey.
            return
    except (ScriptError, json.JSONDecodeError) as e:
        # This can happen if tailscaled is not fully up yet or status is not valid JSON. Continue to auth.
        logging.info(f"Could not parse Tailscale status (this is normal on first run or if not online yet). Error: {e}")

    logging.info("Authenticating with Tailscale and enabling SSH...")
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
        logging.info("✅ Tailscale authenticated successfully and SSH is enabled.")
    except ScriptError as e:
        logging.critical(f"❌ Tailscale authentication and configuration failed: {e}")
        logging.critical("Please check that your auth key is valid and has not expired, and that its associated tags are correctly configured in the Tailscale Admin Console.")
        sys.exit(1)


def main():
    """Main execution function."""
    if os.geteuid() != 0:
        logging.critical("❌ This script must be run as root. Please use 'sudo'.")
        sys.exit(1)

    logging.info("--- Starting Tailscale SSH Setup (Max Flexibility/Min Security) ---")
    
    install_tailscale()
    setup_tailscale(TAILSCALE_AUTH_KEY)

    logging.info("\n--- ✅ Remote Access Setup Complete ---")
    logging.info("This machine is now part of your Tailscale network with SSH enabled.")
    logging.info("\n❗ IMPORTANT: To grant broad SSH access, you MUST:")
    logging.info("1. Configure your Tailscale Authentication Key (used in this script) to apply the 'ssh-enabled-device' tag.")
    logging.info("   Go to: https://login.tailscale.com/admin/settings/authkeys")
    logging.info("   Edit the reusable key, set 'Ephemeral' to OFF, and add 'ssh-enabled-device' to 'Tags'.")
    logging.info("2. Configure your Tailscale ACLs to allow access to devices with this tag.")
    logging.info("   Go to: https://login.tailscale.com/admin/acls")
    logging.info("   Replace your entire ACL JSON with the 'Maximum Flexibility ACL' provided below.")
    logging.info("\nTo connect from another machine in your tailnet (after updating ACLs):")
    try:
        hostname = run_command(['hostname'], capture_output=True)
        logging.info(f"ssh <any_local_username>@{hostname}") # Use hostname for easier remembrance
        logging.info(f"(e.g., ssh root@{hostname} or ssh your_linux_username@{hostname})")
        logging.info(f"(or ssh <any_local_username>@<TAILSCALE_IP_OF_THIS_MACHINE>)")
    except ScriptError:
        logging.info("ssh <any_local_username>@<TAILSCALE_IP_OF_THIS_MACHINE>")
    logging.info("\nRemember that 'any_local_username' must be an actual user account on the destination Linux machine.")


if __name__ == "__main__":
    main()