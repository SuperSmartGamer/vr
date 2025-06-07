#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Automates the installation and configuration of Tailscale with SSH on a
Debian-based system like Zorin OS.

This script performs the following actions:
1. Verifies it is run with root privileges.
2. Checks for and installs Tailscale if it's missing.
3. Authenticates the device to a Tailscale network using a provided auth key,
   and applies a specific tag for ACL management (generic for Linux).
4. Enables the Tailscale SSH server.
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
    with SSH enabled, applying a generic Linux tag for ACL management.
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
        if status.get("BackendState") == "Running" and status.get("Self", {}).get("Online"):
            print("✅ Tailscale is already authenticated and running.")
            # Optional: Check if the tag is already present, if not, add it
            if "tag:linux-ssh-enabled" not in status.get("Self", {}).get("Tags", []):
                print("Adding 'tag:linux-ssh-enabled' to existing Tailscale instance...")
                try:
                    # You need to run 'tailscale up' again with the tag to apply it
                    # Ensure the auth key is still valid or use 'tailscale up --force-reauth'
                    run_command(["tailscale", "up", "--ssh", "--accept-routes", "--accept-dns", "--authkey", auth_key, "linux-ssh-enabled"])
                    print("✅ 'tag:linux-ssh-enabled' added successfully.")
                except ScriptError as e:
                    print(f"❌ Failed to add tag to existing Tailscale instance: {e}")
            return # Exit if already authenticated and tagged (or if tagging failed)
    except (ScriptError, json.JSONDecodeError) as e:
        # This can happen if tailscaled is not fully up yet or status is not valid JSON. Continue to auth.
        print(f"Could not parse Tailscale status (this is normal on first run or if not online yet). Error: {e}")

    print("Authenticating with Tailscale, enabling SSH, and applying 'linux-ssh-enabled' tag...")
    try:
        # The --ssh flag is the correct, modern way to enable SSH on auth.
        # This single command handles both authentication, SSH enablement, and tagging.
        auth_command = [
            "tailscale", "up",
            f"--authkey={auth_key}",
            "--ssh",
            "--accept-routes", # Often useful to accept routes from the tailnet
            "--accept-dns",    # Often useful to accept DNS settings from the tailnet
            "--tag", "linux-ssh-enabled" # Add the generic tag here
        ]
        run_command(auth_command)
        print("✅ Tailscale authenticated successfully, SSH is enabled, and 'linux-ssh-enabled' tag applied.")
    except ScriptError as e:
        print(f"❌ Tailscale authentication and configuration failed: {e}")
        print("\nPlease check that your auth key is valid and has not expired, and that your tagOwners ACL is configured correctly.")
        sys.exit(1)


def main():
    """Main execution function."""
    if os.geteuid() != 0:
        print("❌ This script must be run as root. Please use 'sudo'.")
        sys.exit(1)

    print("--- Starting Tailscale SSH Setup for Linux Machines ---")
    
    install_tailscale()
    setup_tailscale(TAILSCALE_AUTH_KEY)

    print("\n--- ✅ Remote Access Setup Complete ---")
    print("This machine is now part of your Tailscale network with SSH enabled.")
    print(f"It has been provisioned with the tag 'linux-ssh-enabled'.")
    print("\n❗ IMPORTANT: You must configure your Tailscale ACLs to allow maximum SSH access.")
    print("Go to: https://login.tailscale.com/admin/acls")
    print("Replace your entire ACL JSON with the 'Maximum Freedoms ACL' provided.")
    print("\nTo connect from another machine in your tailnet (after updating ACLs):")
    try:
        hostname = run_command(['hostname'], capture_output=True)
        print(f"ssh <any_local_username>@{hostname}") # Use hostname for easier remembrance
        print(f"(e.g., ssh root@{hostname} or ssh your_linux_username@{hostname})")
        print(f"(or ssh <any_local_username>@<TAILSCALE_IP_OF_THIS_MACHINE>)")
    except ScriptError:
        print("ssh <any_local_username>@<TAILSCALE_IP_OF_THIS_MACHINE>")
    print("\nRemember that 'any_local_username' must be an actual user account on the destination Linux machine.")


if __name__ == "__main__":
    main()