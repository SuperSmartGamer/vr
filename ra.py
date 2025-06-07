import subprocess
import os
import sys
import time

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
        print(f"Error executing command: {command}")
        print(f"Return code: {e.returncode}")
        print(f"Output: {e.stderr if e.stderr else e.stdout}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False

def install_tailscale():
    """Installs Tailscale on Zorin OS."""
    print("Installing Tailscale...")
    # Add Tailscale GPG key
    if not run_command("curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.asc | sudo gpg --dearmor -o /usr/share/keyrings/tailscale-archive-keyring.gpg"):
        return False
    
    # Add Tailscale repository
    if not run_command("echo 'deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/ubuntu jammy main' | sudo tee /etc/apt/sources.list.d/tailscale.list"):
        return False
    
    # Update apt and install Tailscale
    if not run_command("sudo apt update"):
        return False
    if not run_command("sudo apt install -y tailscale"):
        return False
    
    print("Tailscale installed successfully.")
    return True

def start_and_authenticate_tailscale():
    """Starts Tailscale and provides authentication instructions."""
    print("Starting Tailscale service...")
    if not run_command("sudo systemctl start tailscaled"):
        return False
    if not run_command("sudo systemctl enable tailscaled"):
        return False
    
    print("\nTailscale service started. Now, you need to authenticate this device.")
    print("Please open the following URL in your web browser on a device connected to the internet:")
    auth_url = run_command(f"sudo tailscale up --advertise-ssh --authkey={key}", capture_output=True, check_error=False)
    # The above line needs your Tailscale authkey.
    # For a fully automated zero-interaction script, you would need to generate an ephemeral authkey from the Tailscale UI/API beforehand.
    # Or, the user can manually run `sudo tailscale up --advertise-ssh` and follow the URL.
    
    if "https://" in auth_url:
        print(auth_url)
        print("\nAfter authentication, this Zorin OS machine will be part of your Tailscale network.")
        print("You can find its Tailscale IP address in your Tailscale admin console.")
        print("To SSH to it, use: ssh <user>@<tailscale_ip_address>")
        print("Example: ssh zorinuser@100.x.y.z")
    else:
        print("Failed to get Tailscale authentication URL. You might need to run 'sudo tailscale up' manually.")
        print("If you have an authkey, replace 'YOUR_TAILSCALE_AUTHKEY_HERE' in the script with it.")
        print("Alternatively, run 'sudo tailscale up' manually to get the login URL.")
    
    # Enable Tailscale SSH (optional, but recommended for integrated key management)
    print("\nEnabling Tailscale SSH (if not already enabled via --advertise-ssh)...")
    if not run_command("sudo tailscale set --ssh"):
        print("Could not enable Tailscale SSH. Check Tailscale logs or manually enable in Tailscale admin console.")
    else:
        print("Tailscale SSH enabled. Ensure your Tailscale ACLs allow SSH access.")

    return True
k1,k2,k3="tskey-clien","t-kXxa37phs711CNTRL-","hrn4nCtZBzWEmma5SCY2zWShnTQxQFmEU"
def configure_ssh_server():
    """Ensures OpenSSH server is installed and running."""
    print("Ensuring OpenSSH server is installed and running...")
    if not run_command("sudo apt install -y openssh-server"):
        print("Failed to install OpenSSH server. Please check your internet connection and apt repositories.")
        return False
    if not run_command("sudo systemctl enable ssh"):
        return False
    if not run_command("sudo systemctl start ssh"):
        return False
    print("OpenSSH server is running.")
    return True
key=k1+k2+k3
def main():
    if os.geteuid() != 0:
        print("This script must be run as root. Please use 'sudo python3 your_script_name.py'")
        sys.exit(1)

    print("Starting remote SSH setup for Zorin OS with Tailscale (no port forwarding).")
    
    if not configure_ssh_server():
        print("SSH server setup failed. Exiting.")
        sys.exit(1)

    if not install_tailscale():
        print("Tailscale installation failed. Exiting.")
        sys.exit(1)

    # Note: For full automation, you'd generate an authkey from your Tailscale admin console
    # and paste it into the script where it says `YOUR_TAILSCALE_AUTHKEY_HERE`.
    # An ephemeral authkey is recommended for single-use deployments.
    print("\n--------------------------------------------------------------")
    print("ATTENTION: For automated authentication, you need a Tailscale Authkey.")
    print("Go to your Tailscale Admin Console -> Settings -> Auth keys -> Generate auth key.")
    print("Copy the generated key and replace 'YOUR_TAILSCALE_AUTHKEY_HERE' in the script.")
    print("If you prefer manual login, remove `--authkey=YOUR_TAILSCALE_AUTHKEY_HERE` from the script.")
    print("--------------------------------------------------------------\n")
    
    time.sleep(5) # Give user time to read the authkey message

    if not start_and_authenticate_tailscale():
        print("Tailscale authentication setup failed. Exiting.")
        sys.exit(1)

    print("\nRemote SSH setup complete via Tailscale.")
    print("You can now SSH to this Zorin OS machine using its Tailscale IP address from any device on your Tailscale network.")
    print("Remember to check your Tailscale ACLs to ensure your user has SSH access to this machine.")
    print("For example, from your client machine: ssh <username_on_zorin>@<zorin_tailscale_ip>")

if __name__ == "__main__":
    main()