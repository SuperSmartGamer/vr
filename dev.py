#!/usr/bin/env python3

import os

def get_local_users():
    """
    Reads the /etc/passwd file to list all local user accounts.

    Returns:
        A list of usernames (strings) if successful, or an empty list if
        the file cannot be read or no users are found.
    """
    users = []
    passwd_file = "/etc/passwd"

    if not os.path.exists(passwd_file):
        print(f"Error: The file '{passwd_file}' does not exist.")
        return []

    try:
        with open(passwd_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line:  # Ensure the line is not empty
                    parts = line.split(':')
                    if len(parts) > 0: # Ensure there's at least a username part
                        username = parts[0]
                        # Optional: You might want to filter out system users.
                        # Common approach is to check UID.
                        # For now, let's list all, but mention filtering.
                        users.append(username)
        return users
    except IOError as e:
        print(f"Error: Could not read '{passwd_file}': {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []

def main():
    """Main function to execute the user listing."""
    print("--- Listing Local User Accounts ---")
    users = get_local_users()

    if users:
        print(f"Found {len(users)} local user(s):")
        for user in users:
            print(f"- {user}")
    else:
        print("No local user accounts found or could not read user information.")
    print("--- End of User List ---")

if __name__ == "__main__":
    main()