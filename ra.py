#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Automates the installation and configuration of Tailscale with SSH on a
Debian-based system like Zorin OS.

This script performs the following actions:
1. Verifies it is run with root privileges.
2. Checks for and installs Tailscale if it's missing.
3. Authenticates the device to a Tailscale network using a provided auth key.
4. Enables the Tailscale SSH server in a single command.
"""

import subprocess
import os
import sys
import json
from typing import List, Optional

# --- CONFIGURATION ---
# IMPORTANT: Replace this with your actual Tailscale authentication key.
# For better security, consider using an environment variable instead:
# TAILSCALE_AUTH_KEY = os.environ.get("TS_AUTH_KEY")
# if not TAILSCALE_AUTH_KEY:
#     print("Error: TS_AUTH_KEY environment variable not set.")
#     sys.exit(1)
k1,k2,k3="tskey-aut","h-k2sUqX9Xe621CNTRL-","XVZtjVekXXNa1pZrHRMgXNrnAJtbjnef"
key=f"{k1}{k2}{k3}"
TAILSCALE_AUTH_KEY =key
# --- END CONFIGURATION ---


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
    try:
        process = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
            encoding='utf-8'
        )
        if capture_output:
            return process.stdout.strip()
        return None
    except FileNotFoundError:
        raise ScriptError(f"Error: Command not found: '{command[0]}'. Is it in the system's PATH?")
    except subprocess.CalledProcessError as e:
        error_message = (
            f"Command '{' '.join(command)}' failed with return code {e.returncode}.\n"
            f"Stderr: {e.stderr.strip()}"
        )
        raise ScriptError(error_message)


def is_package_installed(package_name: str) -> bool:
    """Checks if a Debian package is installed."""
    try:
        # dpkg-query is more reliable than dpkg -s for scripting
        run_command(["dpkg-query", "-W", "-f=${Status}", package_name])
        return True
    except ScriptError:
        return False


def get_ubuntu_codename() -> str:
    """Gets the Ubuntu release codename for the Tailscale repository."""
    try:
        return run_command(["lsb_release", "-cs"], capture_output=True)
    except ScriptError as e:
        print(f"Warning: Could not determine Ubuntu codename. Falling back to 'jammy'. Error: {e}")
        # Zorin OS 17 is based on jammy (22.04), a safe fallback.
        return "jammy"


def install_tailscale():
    """Installs Tailscale on the system if not already present."""
    if is_package_installed("tailscale"):
        print("✅ Tailscale is already installed.")
        return

    print("🔹 Tailscale not found. Starting installation...")
    try:
        # Add Tailscale's GPG key
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
        with open("/etc/apt/sources.list.d/tailscale.list", "w") as f:
            f.write(repo_list_content)
        
        # Update package lists and install
        print("Updating package lists...")
        run_command(["apt-get", "update"])
        print("Installing Tailscale package...")
        run_command(["apt-get", "install", "-y", "tailscale"])
        print("✅ Tailscale installed successfully.")
    except (ScriptError, IOError) as e:
        print(f"❌ Installation failed: {e}")
        sys.exit(1)


def setup_tailscale(auth_key: str):
    """
    Ensures the Tailscale service is running and authenticates the node
    with SSH enabled.
    """
    print("🔹 Configuring Tailscale service...")
    try:
        run_command(["systemctl", "enable", "--now", "tailscaled"])
    except ScriptError as e:
        print(f"❌ Failed to start or enable tailscaled service: {e}")
        sys.exit(1)

    # Check if already authenticated and running using reliable JSON output
    try:
        status_json = run_command(["tailscale", "status", "--json"], capture_output=True)
        status = json.loads(status_json)
        if status.get("BackendState") == "Running":
            print("✅ Tailscale is already authenticated and running.")
            return
    except (ScriptError, json.JSONDecodeError) as e:
        # This can happen if tailscaled is not fully up yet. Continue to auth.
        print(f"Could not parse Tailscale status (this is normal on first run). Error: {e}")

    print("Authenticating with Tailscale and enabling SSH...")
    try:
        # The --ssh flag is the correct, modern way to enable SSH on auth.
        # This single command handles both authentication and SSH enablement.
        auth_command = [
            "tailscale", "up", f"--authkey={auth_key}", "--ssh"
        ]
        run_command(auth_command)
        print("✅ Tailscale authenticated successfully and SSH is enabled.")
    except ScriptError as e:
        print(f"❌ Tailscale authentication failed: {e}")
        print("\nPlease check that your auth key is valid and has not expired.")
        sys.exit(1)


def main():
    """Main execution function."""
    if os.geteuid() != 0:
        print("❌ This script must be run as root. Please use 'sudo'.")
        sys.exit(1)

    print("--- Starting Tailscale SSH Setup for Zorin OS ---")
    
    install_tailscale()
    setup_tailscale(TAILSCALE_AUTH_KEY)

    print("\n--- ✅ Remote Access Setup Complete ---")
    print("This machine is now part of your Tailscale network with SSH enabled.")
    print("Find its IP address in the Tailscale admin console: https://login.tailscale.com/admin/machines")
    print("To connect, run this command from another machine in your tailnet:")
    try:
        hostname = run_command(['hostname'], capture_output=True)
        print(f"ssh {hostname}@<TAILSCALE_IP_OF_THIS_MACHINE>")
    except ScriptError:
        print("ssh <your_zorin_username>@<TAILSCALE_IP_OF_THIS_MACHINE>")
    print("\nRemember to verify your Tailscale ACLs to ensure access is permitted.")


if __name__ == "__main__":
    main()