import subprocess
import os
import sys
import time



k1,k2,k3="tskey-aut","h-k2sUqX9Xe621CNTRL-","XVZtjVekXXNa1pZrHRMgXNrnAJtbjnef"
key=f"{k1}{k2}{k3}"
# ------------------------------------------
print(key)


def run_command(command, check_error=True, capture_output=False):
    """Helper function to run shell commands."""
    try:
        if capture_output:
            result = subprocess.run(command, shell=True, check=check_error, text=True, capture_output=True)
            return result.stdout.strip()
        else:
            subprocess.run(command, shell=True, check=check_error)
        return True
    except subprocess.CalledProcessError as e:
        # print(f"Error executing command: {command}")
        # print(f"Return code: {e.returncode}")
        # print(f"Output: {e.stderr if e.stderr else e.stdout}")
        return False # Return False on error for checks
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False

def is_package_installed(package_name):
    """Checks if a debian package is installed."""
    return run_command(f"dpkg -s {package_name}", check_error=False, capture_output=True)

def is_service_active(service_name):
    """Checks if a systemd service is active."""
    return "active" in run_command(f"systemctl is-active {service_name}", check_error=False, capture_output=True)

def install_tailscale():
    """Installs Tailscale on Zorin OS if not already installed."""
    if is_package_installed("tailscale"):
        print("Tailscale is already installed. Skipping installation.")
        return True
    
    print("Tailscale not found. Installing Tailscale...")
    # Add Tailscale GPG key
    if not run_command("curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.asc | sudo gpg --dearmor -o /usr/share/keyrings/tailscale-archive-keyring.gpg"):
        print("Failed to add Tailscale GPG key.")
        return False
    
    # Add Tailscale repository
    if not run_command("echo 'deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/ubuntu jammy main' | sudo tee /etc/apt/sources.list.d/tailscale.list"):
        print("Failed to add Tailscale repository.")
        return False
    
    # Update apt and install Tailscale
    if not run_command("sudo apt update"):
        print("Failed to update apt repositories.")
        return False
    if not run_command("sudo apt install -y tailscale"):
        print("Failed to install Tailscale package.")
        return False
    
    print("Tailscale installed successfully.")
    return True

def start_and_authenticate_tailscale(auth_key):
    """Starts Tailscale and attempts authentication using the provided auth_key."""
    if is_service_active("tailscaled"):
        print("Tailscale service is already running.")
    else:
        print("Starting Tailscale service...")
        if not run_command("sudo systemctl start tailscaled"):
            print("Failed to start tailscaled service.")
            return False
        if not run_command("sudo systemctl enable tailscaled"):
            print("Failed to enable tailscaled service.")
            return False
    
    # Check if already authenticated (simplified check, might not catch all states)
    status_output = run_command("sudo tailscale status", capture_output=True, check_error=False)
    if "Logged in as" in status_output and "active" in status_output:
        print("Tailscale is already authenticated and active.")
    else:
        print("\nAttempting to authenticate Tailscale with provided key...")
        # Use f-string to insert the auth_key variable
        auth_command = f"sudo tailscale up --advertise-ssh --authkey={auth_key}"
        auth_output = run_command(auth_command, capture_output=True, check_error=False)
        
        if "Success." in auth_output or "already authenticated" in auth_output or "active" in auth_output:
            print("Tailscale authenticated successfully!")
            print("This Zorin OS machine should now be part of your Tailscale network.")
            print("You can find its Tailscale IP address in your Tailscale admin console.")
        else:
            print("Tailscale authentication via authkey failed or did not provide immediate success message.")
            print("Output of tailscale up command:\n", auth_output)
            print("\nPlease check the auth key or consider running 'sudo tailscale up' manually to get a login URL if needed.")
            print("If you run it manually, open the URL in your web browser on a device connected to the internet to authenticate.")
    
    # Enable Tailscale SSH (optional, but recommended for integrated key management)
    print("\nEnabling Tailscale SSH (if not already enabled via --advertise-ssh)...")
    if not run_command("sudo tailscale set --ssh"):
        print("Could not enable Tailscale SSH. Check Tailscale logs or manually enable in Tailscale admin console.")
    else:
        print("Tailscale SSH enabled. Ensure your Tailscale ACLs allow SSH access.")

    return True

def configure_ssh_server():
    """Ensures OpenSSH server is installed and running."""
    if is_package_installed("openssh-server"):
        print("OpenSSH server is already installed.")
    else:
        print("OpenSSH server not found. Installing OpenSSH server...")
        if not run_command("sudo apt install -y openssh-server"):
            print("Failed to install OpenSSH server. Please check your internet connection and apt repositories.")
            return False
    
    if is_service_active("ssh"):
        print("OpenSSH service is already running.")
    else:
        print("Starting OpenSSH service...")
        if not run_command("sudo systemctl enable ssh"):
            print("Failed to enable OpenSSH service.")
            return False
        if not run_command("sudo systemctl start ssh"):
            print("Failed to start OpenSSH service.")
            return False
    
    print("OpenSSH server is ready.")
    return True

def main():
    if os.geteuid() != 0:
        print("This script must be run as root. Please use 'sudo python3 your_script_name.py'")
        sys.exit(1)

    # --- DEFINE YOUR TAILSCALE AUTH KEY HERE ---
    # Replace 'YOUR_ACTUAL_TAILSCALE_AUTH_KEY' with the key you generated from your Tailscale admin console.


    if key == 'YOUR_ACTUAL_TAILSCALE_AUTH_KEY' or not key:
        print("ERROR: Please replace 'YOUR_ACTUAL_TAILSCALE_AUTH_KEY' with your actual Tailscale auth key in the script.")
        sys.exit(1)

    print("Starting remote SSH setup for Zorin OS with Tailscale (no port forwarding).")
    
    if not configure_ssh_server():
        print("SSH server setup failed. Exiting.")
        sys.exit(1)

    if not install_tailscale():
        print("Tailscale installation failed. Exiting.")
        sys.exit(1)

    if not start_and_authenticate_tailscale(key): # Pass the 'key' variable
        print("Tailscale authentication setup failed. Exiting.")
        # Note: We don't sys.exit(1) here if authentication fails,
        # as the user might manually authenticate later with `tailscale up`.
        # However, for a fully automated run, you might want to exit.
        # I've kept it as it was for consistency with previous behavior.
        sys.exit(1)

    print("\nRemote SSH setup complete via Tailscale.")
    print("You can now SSH to this Zorin OS machine using its Tailscale IP address from any device on your Tailscale network.")
    print("Remember to check your Tailscale ACLs (Access Controls) in your Tailscale admin console to ensure your user has SSH access to this machine.")
    print("For example, from your client machine: ssh <username_on_zorin>@<zorin_tailscale_ip>")

if __name__ == "__main__":
    main()
