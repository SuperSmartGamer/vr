#!/usr/bin/env python3

import pwd
import sys
import os
import datetime
import atexit # Import atexit to register cleanup functions

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
        self.closed = False # Track if the Tee is closed

    def write(self, data):
        if not self.closed:
            self.primary_stream.write(data)
            self.secondary_stream.write(data)

    def flush(self, *args, **kwargs):
        if not self.closed:
            self.primary_stream.flush(*args, **kwargs)
            self.secondary_stream.flush(*args, **kwargs)

    def close(self):
        # Prevent writing after close and ensure file stream is closed
        if not self.closed:
            self.flush() # Flush one last time
            if hasattr(self.secondary_stream, 'close'):
                self.secondary_stream.close()
            self.closed = True

# Store the original stdout/stderr so we can restore them at the end
_original_stdout = sys.stdout
_original_stderr = sys.stderr
_log_file_handle = None # To hold the file object

def setup_logging(log_filename="debug.txt"):
    """
    Sets up logging to redirect stdout and stderr to a specified file
    in the script's directory, while also printing to the console.
    Registers a cleanup function using atexit.
    """
    global _log_file_handle # Declare that we are modifying the global variable
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(script_dir, log_filename)

    try:
        # Open the log file in append mode ('a') for continuous logging
        # buffering=1 means line-buffered, which is good for real-time viewing
        _log_file_handle = open(log_file_path, "a", buffering=1, encoding='utf-8')
    except IOError as e:
        # If the log file cannot be opened, print an error to original stderr
        # and revert to original stdout/stderr for all subsequent output.
        print(f"Error: Could not open log file '{log_file_path}' for writing: {e}", file=_original_stderr)
        return

    # Create Tee objects to redirect output
    sys.stdout = Tee(_original_stdout, _log_file_handle)
    sys.stderr = Tee(_original_stderr, _log_file_handle)

    # Register a cleanup function to ensure logs are flushed and file is closed
    atexit.register(cleanup_logging)

    sys.stdout.write(f"\n--- Log started at {datetime.datetime.now()} ---\n")
    sys.stdout.write(f"All output for this run will be saved to: {log_file_path}\n")
    sys.stdout.flush() # Ensure this initial message is written

def cleanup_logging():
    """
    Function to be called on script exit to ensure streams are flushed and closed.
    """
    if isinstance(sys.stdout, Tee):
        sys.stdout.close()
    if isinstance(sys.stderr, Tee):
        sys.stderr.close()

    # Restore original streams to avoid affecting other parts of the system
    sys.stdout = _original_stdout
    sys.stderr = _original_stderr

def get_all_users(include_system_users: bool = False, min_uid: int = 1000) -> list:
    """
    Retrieves a list of all users on the system.

    Args:
        include_system_users: If True, includes system users (UID < min_uid).
                              If False, only includes "regular" users.
        min_uid: The minimum User ID (UID) to consider for regular users.
                 Commonly 1000 on modern Linux distributions.

    Returns:
        A list of dictionaries, where each dictionary contains user details.
    """
    users_list = []
    print("\n[INFO] Retrieving user information...")
    try:
        for user_entry in pwd.getpwall():
            uid = user_entry.pw_uid
            username = user_entry.pw_name
            home_dir = user_entry.pw_dir
            shell = user_entry.pw_shell
            gecos = user_entry.pw_gecos # GECOS field (usually full name/comment)

            is_system_user = uid < min_uid

            if not include_system_users and is_system_user:
                continue # Skip system users if not requested

            users_list.append({
                "username": username,
                "uid": uid,
                "gid": user_entry.pw_gid,
                "full_name": gecos,
                "home_directory": home_dir,
                "shell": shell,
                "is_system_user": is_system_user
            })
        print("✅ User information retrieved successfully.")
    except Exception as e:
        error_msg = f"❌ Failed to retrieve user information: {e}"
        print(error_msg, file=sys.stderr)
        raise ScriptError(error_msg)

    users_list.sort(key=lambda x: x['username'])
    return users_list

def main():
    """Main execution function."""
    # Setup logging first, so all subsequent prints are captured
    setup_logging(log_filename="debug.txt")

    try:
        print("--- Starting User Listing Script ---")

        print("\n--- Regular Users (UID >= 1000) ---")
        regular_users = get_all_users(include_system_users=False)
        if regular_users:
            for user in regular_users:
                print(f"  Username: {user['username']}")
                print(f"    UID: {user['uid']}, GID: {user['gid']}")
                print(f"    Full Name: {user['full_name'] if user['full_name'] else 'N/A'}")
                print(f"    Home Dir: {user['home_directory']}")
                print(f"    Shell: {user['shell']}")
                print("-" * 20)
        else:
            print("No regular users found.")

        print("\n--- All Users (Including System Users) ---")
        all_users = get_all_users(include_system_users=True)
        if all_users:
            for user in all_users:
                user_type = "System User" if user['is_system_user'] else "Regular User"
                print(f"  Username: {user['username']} ({user_type})")
                print(f"    UID: {user['uid']}, GID: {user['gid']}")
                print(f"    Full Name: {user['full_name'] if user['full_name'] else 'N/A'}")
                print(f"    Home Dir: {user['home_directory']}")
                print(f"    Shell: {user['shell']}")
                print("-" * 20)
        else:
            print("No users found on the system.")

        print("\n--- ✅ User Listing Complete ---")

    except ScriptError as e:
        # ScriptError is already logged by the function that raised it
        sys.exit(1) # Exit with a non-zero code to indicate failure
    except Exception as e:
        # Catch any other unexpected errors
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1) # Exit with a non-zero code for unexpected errors

if __name__ == "__main__":
    main()