import subprocess
import threading
import time
import logging
import os
import datetime
import sys
import tempfile
import io
import hashlib

# --- Logging Setup (Embedded) ---
UNIFIED_LOG_FILE = "thing.txt"
CONSOLE_LOG_FILE = "console.log"

class CustomFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ct = datetime.datetime.fromtimestamp(record.created)
        if datefmt:
            s = ct.strftime(datefmt)
        else:
            s = ct.strftime("%Y-%m-%d %H:%M:%S")
        return f"{s}.{int(record.msecs):02d}"

def setup_logging(script_name):
    """
    Sets up the logging configuration for the script, directing logs to a unified file,
    a console-specific file, and the standard output.
    """
    # Ensure handlers are not duplicated if called multiple times in same process
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    try:
        unified_handler = logging.FileHandler(UNIFIED_LOG_FILE, encoding="utf-8")
        unified_handler.setFormatter(CustomFormatter(fmt='%(asctime)s - %(levelname)s - %(message)s'))
        unified_handler.setLevel(logging.INFO)
    except IOError as e:
        logging.critical(f"LOG_ERROR: Failed to open unified log file '{UNIFIED_LOG_FILE}': {e}. Logging to this file will be disabled.", exc_info=True)
        unified_handler = None

    try:
        console_handler = logging.FileHandler(CONSOLE_LOG_FILE, encoding="utf-8")
        console_handler.setFormatter(CustomFormatter(fmt=f'%(asctime)s - {script_name} - %(levelname)s - %(message)s'))
        console_handler.setLevel(logging.DEBUG)
    except IOError as e:
        logging.critical(f"LOG_ERROR: Failed to open console log file '{CONSOLE_LOG_FILE}': {e}. Logging to this file will be disabled.", exc_info=True)
        console_handler = None

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(CustomFormatter(fmt=f'%(asctime)s - {script_name} - %(levelname)s - %(message)s'))
    stream_handler.setLevel(logging.INFO)

    handlers = [h for h in [unified_handler, console_handler, stream_handler] if h is not None]
    
    if not handlers:
        # Fallback if no handlers could be set up (e.g., permission issues for both files)
        logging.basicConfig(level=logging.CRITICAL, format='%(asctime)s - %(levelname)s - %(message)s')
        logging.critical("LOG_ERROR: No log handlers could be initialized. All logging may be directed to stderr.")
    else:
        logging.basicConfig(
            level=logging.DEBUG, # Set base level to DEBUG to allow all handlers to filter
            handlers=handlers
        )
# --- End of Logging Setup ---

setup_logging("CLIPBOARD_MONITOR")
log_write_lock = threading.Lock() # Protects log file writes from multiple threads

# --- Centralized Error Handling Function ---
def handle_error(component, message, level=logging.ERROR, exc_info=True):
    """
    Centralized function for logging errors consistently.
    Args:
        component (str): The part of the script where the error occurred (e.g., "CLIPBOARD_MONITOR", "UPLOAD").
        message (str): A description of the error.
        level (int): The logging level (e.g., logging.ERROR, logging.CRITICAL).
        exc_info (bool): Whether to include exception info (stack trace) in the log.
    """
    with log_write_lock:
        logging.log(level, f"{component}_ERROR: {message}", exc_info=exc_info)


# Platform detection
IS_WINDOWS = sys.platform == 'win32'
IS_LINUX = sys.platform.startswith('linux')

# --- Attempt Imports with Error Handling ---
HAS_CLIPBOARD_MONITOR = False
if IS_LINUX: # clipboard-monitor is Linux-specific
    try:
        import clipboard_monitor # The external library
        HAS_CLIPBOARD_MONITOR = True
        logging.debug("CLIPBOARD: Successfully imported 'clipboard_monitor' library.")
    except ImportError as e:
        handle_error("CLIPBOARD", f"Failed to import 'clipboard_monitor' library ({e}). Event-driven clipboard monitoring will be disabled.", logging.WARNING)
    except Exception as e:
        handle_error("CLIPBOARD", f"An unexpected error occurred during 'clipboard_monitor' import: {e}. Event-driven monitoring disabled.", logging.ERROR)
else:
    logging.debug("CLIPBOARD: Running on non-Linux OS. 'clipboard_monitor' library will not be used.")

HAS_PIL = False
try:
    from PIL import Image, ImageGrab
    HAS_PIL = True
    logging.debug("CLIPBOARD: Successfully imported 'Pillow' (PIL).")
except ImportError as e:
    handle_error("CLIPBOARD", f"Failed to import 'Pillow' (PIL) library ({e}). Image clipboard saving/uploading will be disabled.", logging.WARNING)
except Exception as e:
    handle_error("CLIPBOARD", f"An unexpected error occurred during 'Pillow' import: {e}. Image features disabled.", logging.ERROR)

HAS_PYPERCLIP = False
try:
    import pyperclip
    HAS_PYPERCLIP = True
    logging.debug("CLIPBOARD: Successfully imported 'pyperclip'.")
except ImportError as e:
    handle_error("CLIPBOARD", f"Failed to import 'pyperclip' library ({e}). Initial clipboard content and general fallback may be limited.", logging.WARNING)
except Exception as e:
    handle_error("CLIPBOARD", f"An unexpected error occurred during 'pyperclip' import: {e}. Text clipboard features limited.", logging.ERROR)

HAS_UPLOAD_PY = False
try:
    import upload # Assuming upload.py is in the same directory
    if hasattr(upload, 'upload_to_r2') and callable(upload.upload_to_r2):
        HAS_UPLOAD_PY = True
        logging.debug("CLIPBOARD: Successfully imported 'upload.py' and found 'upload_to_r2'.")
    else:
        handle_error("CLIPBOARD", "'upload.py' found, but 'upload_to_r2' function not found or not callable within it. Image upload disabled.", logging.WARNING, exc_info=False)
except ImportError as e:
    handle_error("CLIPBOARD", f"Failed to import 'upload.py' ({e}). Image upload functionality will be disabled.", logging.WARNING)
except Exception as e:
    handle_error("CLIPBOARD", f"An unexpected error occurred while importing 'upload.py': {e}. Image upload functionality disabled.", logging.ERROR)

HAS_WL_PASTE = False
HAS_XCLIP = False

# --- Configuration ---
POLLING_INTERVAL_SECONDS = 1
MAX_COMMAND_TIMEOUT = 5 # Increased timeout slightly for CLI commands

# --- Global Variables ---
last_clipboard_content_polled = ""
last_clipboard_image_hash = None

# --- Helper to execute shell commands ---
def run_command(command, check_success=True):
    """
    Executes a shell command and returns its stdout.
    Only attempts on Linux to avoid errors on Windows.
    Handles various subprocess errors.
    """
    if not IS_LINUX:
        logging.debug(f"COMMAND: Skipping Linux command '{command}' on non-Linux OS.")
        return None
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=check_success, shell=True, timeout=MAX_COMMAND_TIMEOUT)
        if check_success and result.returncode != 0:
            handle_error("COMMAND", f"Command '{command}' failed with exit code {result.returncode}. Stderr: {result.stderr.strip()}", logging.DEBUG, exc_info=False)
            return None
        return result.stdout.strip()
    except FileNotFoundError:
        handle_error("COMMAND", f"Command '{command.split(' ')[0]}' not found. Ensure it's installed and in PATH.", logging.WARNING)
        return None
    except subprocess.CalledProcessError as e:
        handle_error("COMMAND", f"Command '{command}' failed (exit code {e.returncode}). Stderr: {e.stderr.strip()}", logging.WARNING)
        return None
    except subprocess.TimeoutExpired:
        handle_error("COMMAND", f"Command '{command}' timed out after {MAX_COMMAND_TIMEOUT} seconds.", logging.WARNING)
        return None
    except Exception as e:
        handle_error("COMMAND", f"Unexpected error running command '{command}': {e}", logging.ERROR)
        return None

# --- Runtime check for Linux CLI tools ---
def check_linux_cli_tools():
    """
    Checks for the presence of necessary command-line clipboard tools on Linux.
    """
    global HAS_WL_PASTE, HAS_XCLIP
    if IS_LINUX:
        # Check for wl-paste
        try:
            if run_command("command -v wl-paste", check_success=True) is not None:
                HAS_WL_PASTE = True
                logging.debug("CLIPBOARD: 'wl-paste' command found.")
            else:
                logging.warning("CLIPBOARD: 'wl-paste' command not found. Wayland text clipboard access may be limited.")
        except Exception as e:
            handle_error("CLIPBOARD", f"Error checking for 'wl-paste': {e}", logging.WARNING)

        # Check for xclip or xsel
        try:
            if run_command("command -v xclip", check_success=True) is not None:
                HAS_XCLIP = True
                logging.debug("CLIPBOARD: 'xclip' command found.")
            elif run_command("command -v xsel", check_success=True) is not None:
                HAS_XCLIP = True
                logging.debug("CLIPBOARD: 'xsel' command found.")
            else:
                logging.warning("CLIPBOARD: 'xclip' or 'xsel' commands not found. X11 text clipboard access may be limited.")
        except Exception as e:
            handle_error("CLIPBOARD", f"Error checking for 'xclip'/'xsel': {e}", logging.WARNING)
    else:
        logging.debug("CLIPBOARD: Skipping Linux CLI tool checks on non-Linux OS.")

# --- Helper for Image Hashing ---
def _get_image_hash(pil_image):
    """
    Calculates a SHA256 hash of a PIL Image object by saving it to an in-memory PNG.
    Returns None if image is invalid or an error occurs.
    """
    if not pil_image:
        logging.debug("CLIPBOARD: No PIL image provided for hashing.")
        return None
    try:
        img_byte_arr = io.BytesIO()
        pil_image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        return hashlib.sha256(img_byte_arr).hexdigest()
    except Exception as e:
        handle_error("IMAGE_HASH", f"Error hashing image: {e}")
        return None

# --- Clipboard Monitoring Callbacks/Polling ---
def log_clipboard_event(prefix, content=None):
    """Logs various clipboard events with appropriate formatting."""
    with log_write_lock:
        if "Image Changed" in prefix:
            logging.info(f"CLIPBOARD: {prefix}")
        elif isinstance(content, list):
            logging.info(f"CLIPBOARD: {prefix} - {len(content)} Files:")
            for item in content:
                logging.info(f"  - {item}")
        elif isinstance(content, str):
            display_content = content[:100] + "..." if len(content) > 100 else content
            logging.info(f"CLIPBOARD: {prefix} - Text: '{display_content}'")
        else:
            logging.info(f"CLIPBOARD: {prefix} - Type: {type(content).__name__} (Content may not be directly loggable)")

# These functions are designed to be used by event-driven clipboard_monitor (Linux)
# OR manually called by the polling loop (Windows/Linux fallback)
def on_text_change_clipboard_monitor(text):
    """Callback for text changes from event-driven monitor."""
    log_clipboard_event("Event-Driven Text Changed", text)

def on_files_change_clipboard_monitor(files):
    """Callback for file changes from event-driven monitor."""
    log_clipboard_event("Event-Driven Files Changed", files)

def on_image_change_clipboard_monitor():
    """
    Callback for image changes detected by clipboard-monitor OR by polling.
    Saves image to a temporary file, uploads it, and then deletes the temporary file.
    """
    current_time_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_clipboard_event(f"Image Changed at {current_time_str}")

    if not HAS_PIL:
        logging.info("CLIPBOARD: Image change detected, but Pillow library not available for processing.")
        return

    temp_file_path = None
    try:
        image = ImageGrab.grabclipboard()
        if image:
            # Use tempfile.NamedTemporaryFile with 'delete=False' then explicitly remove
            # This helps ensure the file object is closed before os.remove on Windows
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png", mode='wb') as temp_file:
                temp_file_path = temp_file.name
                image.save(temp_file) # Save directly to the file object
            
            logging.info(f"CLIPBOARD: Image temporarily saved to {os.path.basename(temp_file_path)} for upload.")

            if HAS_UPLOAD_PY:
                try:
                    upload_success = upload.upload_to_r2(temp_file_path)
                    if upload_success:
                        logging.info(f"CLIPBOARD: Image {os.path.basename(temp_file_path)} successfully uploaded to R2.")
                    else:
                        handle_error("UPLOAD", f"Image {os.path.basename(temp_file_path)} upload to R2 failed.", logging.WARNING, exc_info=False)
                except Exception as upload_e:
                    handle_error("UPLOAD", f"Error during R2 upload of {os.path.basename(temp_file_path)}: {upload_e}")
            else:
                logging.warning("CLIPBOARD: 'upload.py' not available or 'upload_to_r2' function missing. Image not uploaded.")
        else:
            logging.info("CLIPBOARD: No image data found on clipboard or image format not supported by Pillow.")
    except Exception as e:
        handle_error("CLIPBOARD", f"Error processing/uploading image from clipboard: {e}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logging.debug(f"CLIPBOARD: Temporary image file {os.path.basename(temp_file_path)} deleted.")
            except OSError as e:
                handle_error("FILE_SYSTEM", f"Error deleting temporary image file {os.path.basename(temp_file_path)}: {e}", logging.ERROR, exc_info=True)
            except Exception as e:
                handle_error("FILE_SYSTEM", f"Unexpected error deleting temporary image file {os.path.basename(temp_file_path)}: {e}", logging.ERROR, exc_info=True)


def get_current_clipboard_content():
    """
    Tries to get the current clipboard text content using available methods.
    Prioritizes pyperclip (cross-platform), then Linux CLI tools.
    Returns None if no content or an error occurs.
    """
    # 1. Try pyperclip
    if HAS_PYPERCLIP:
        try:
            content = pyperclip.paste()
            logging.debug("CLIPBOARD: Got text via pyperclip.")
            return content
        except pyperclip.PyperclipException as e:
            handle_error("CLIPBOARD", f"pyperclip.paste() failed: {e}. Trying next method.", logging.DEBUG, exc_info=True)
        except Exception as e:
            handle_error("CLIPBOARD", f"Unexpected error with pyperclip.paste(): {e}. Trying next method.", logging.ERROR)

    # 2. Try Linux CLI tools (if on Linux)
    if IS_LINUX:
        if HAS_WL_PASTE:
            content = run_command("wl-paste -n", check_success=False)
            if content is not None:
                logging.debug("CLIPBOARD: Got text via wl-paste.")
                return content
            else:
                logging.debug("CLIPBOARD: wl-paste returned no content or failed.")

        if HAS_XCLIP:
            # xclip requires selecting the clipboard explicitly; 'clipboard' is the default for text
            content = run_command("xclip -o -selection clipboard", check_success=False)
            if content is not None:
                logging.debug("CLIPBOARD: Got text via xclip.")
                return content
            else:
                logging.debug("CLIPBOARD: xclip returned no content or failed.")
    
    logging.debug("CLIPBOARD: No reliable text clipboard tool/method found or all failed to get content.")
    return None

def poll_clipboard_content_loop():
    """
    Main loop for polling clipboard content (text and images).
    This loop will be the primary mechanism on Windows and a fallback on Linux.
    Handles errors within each polling iteration to ensure continuous operation.
    """
    global last_clipboard_content_polled, last_clipboard_image_hash
    logging.info(f"CLIPBOARD: Polling loop started with interval {POLLING_INTERVAL_SECONDS} seconds.")
    while True:
        try:
            # --- Poll for Text Changes ---
            try:
                current_clipboard_text = get_current_clipboard_content()
                if current_clipboard_text is not None and current_clipboard_text != last_clipboard_content_polled:
                    log_clipboard_event("Polled Text Change", current_clipboard_text)
                    last_clipboard_content_polled = current_clipboard_text
                    # If text changed, reset image hash (new clipboard content usually means new overall content)
                    last_clipboard_image_hash = None
            except Exception as e:
                handle_error("CLIPBOARD_POLL", f"Error during text clipboard polling: {e}", logging.ERROR)
            
            # --- Poll for Image Changes (only if Pillow is available) ---
            if HAS_PIL:
                current_clipboard_image = None
                try:
                    current_clipboard_image = ImageGrab.grabclipboard()
                except Exception as e:
                    # This often fails if the clipboard contains non-image data. Log as debug.
                    logging.debug(f"CLIPBOARD_POLL: ImageGrab.grabclipboard() failed (possibly non-image data): {e}")
                
                if current_clipboard_image:
                    current_image_hash = _get_image_hash(current_clipboard_image)
                    if current_image_hash and current_image_hash != last_clipboard_image_hash:
                        logging.info("CLIPBOARD: Polled Image Change Detected.")
                        # This callback handles saving, uploading, and deleting temp file
                        on_image_change_clipboard_monitor()
                        last_clipboard_image_hash = current_image_hash
                    elif current_image_hash is None:
                        logging.debug("CLIPBOARD: Current image could not be hashed after grab. Potentially invalid or empty.")
                elif last_clipboard_image_hash is not None: # If there was an image, but now there isn't
                    logging.debug("CLIPBOARD: Polled image content is now empty or unrecognized.")
                    last_clipboard_image_hash = None # Reset hash
            
        except Exception as e:
            # This catches errors in the main polling loop's outer try block
            handle_error("CLIPBOARD_POLL", f"Unhandled error in polling loop iteration: {e}", logging.CRITICAL)
            # Consider a small delay or mechanism to prevent rapid error looping if a persistent issue arises
            time.sleep(POLLING_INTERVAL_SECONDS * 2) # Longer delay on unhandled error
        
        time.sleep(POLLING_INTERVAL_SECONDS)

# --- Main Execution Block ---
if __name__ == "__main__":
    logging.info("--- Starting Clipboard Monitor ---")
    logging.info(f"Main activity log: {os.path.abspath(UNIFIED_LOG_FILE)}")
    logging.info(f"Error/Debug log: {os.path.abspath(CONSOLE_LOG_FILE)}")
    logging.info("Press Ctrl+C to stop.")

    if IS_WINDOWS:
        logging.info("CLIPBOARD: Running on Windows. Polling will be the primary clipboard monitoring method.")
    elif IS_LINUX:
        logging.info("CLIPBOARD: Running on Linux. Will attempt event-driven monitoring first, then fallback to polling.")
        check_linux_cli_tools() # Check Linux CLI tools only on Linux
    else:
        logging.warning(f"CLIPBOARD: Running on unsupported OS: {sys.platform}. Clipboard monitoring may not work as expected.")

    # Log initial clipboard content (text and image if present)
    logging.info("CLIPBOARD: Attempting to get initial clipboard content...")
    initial_clipboard_text = get_current_clipboard_content()
    if initial_clipboard_text is not None:
        log_clipboard_event("Initial Text Content", initial_clipboard_text)
        last_clipboard_content_polled = initial_clipboard_text
    else:
        logging.warning("CLIPBOARD: Could not get initial text clipboard content via any method available.")

    if HAS_PIL:
        initial_clipboard_image = None
        try:
            initial_clipboard_image = ImageGrab.grabclipboard()
        except Exception as e:
            logging.warning(f"CLIPBOARD: Failed to get initial image clipboard content: {e}", exc_info=True)

        if initial_clipboard_image:
            last_clipboard_image_hash = _get_image_hash(initial_clipboard_image)
            if last_clipboard_image_hash:
                log_clipboard_event("Initial Image Content", f"Hash: {last_clipboard_image_hash[:8]}...")
            else:
                logging.warning("CLIPBOARD: Initial image content found but could not be hashed.")
        else:
            logging.info("CLIPBOARD: No initial image content on clipboard.")
    else:
        logging.info("CLIPBOARD: Skipping initial image content check as Pillow is not available.")

    monitoring_method_started = False
    # Only attempt event-driven clipboard_monitor if on Linux and it's available
    if IS_LINUX and HAS_CLIPBOARD_MONITOR:
        try:
            clipboard_monitor.on_text(on_text_change_clipboard_monitor)
            clipboard_monitor.on_files(on_files_change_clipboard_monitor)
            clipboard_monitor.on_image(on_image_change_clipboard_monitor)
            logging.info("CLIPBOARD: Attempting clipboard monitoring with 'clipboard_monitor' (event-driven).")
            monitoring_method_started = True
            clipboard_monitor.wait() # This is a blocking call
        except KeyboardInterrupt:
            logging.info("CLIPBOARD: KeyboardInterrupt detected during 'clipboard_monitor.wait()'. Shutting down.")
            monitoring_method_started = True # Mark as started to avoid polling fallback
        except Exception as e:
            handle_error("CLIPBOARD_MONITOR", f"'clipboard_monitor' failed during wait cycle ({e}). Falling back to polling.", logging.ERROR)
            HAS_CLIPBOARD_MONITOR = False # Mark as failed so it's not re-attempted
            monitoring_method_started = False

    # Always start polling if event-driven didn't start (or on Windows where it's not available)
    if not monitoring_method_started:
        # Check if at least one method for text OR image is available for polling to be useful
        if (HAS_PYPERCLIP or HAS_PIL or (IS_LINUX and (HAS_WL_PASTE or HAS_XCLIP))):
            logging.info("CLIPBOARD: Starting clipboard monitoring via polling.")
            try:
                poll_clipboard_content_loop()
            except KeyboardInterrupt:
                logging.info("CLIPBOARD: KeyboardInterrupt detected during polling loop. Shutting down.")
            except Exception as e:
                handle_error("MAIN_LOOP", f"A critical error occurred in clipboard polling loop: {e}", logging.CRITICAL)
        else:
            handle_error("INITIALIZATION", "No working clipboard monitoring method found (pyperclip, PIL, or Linux CLI tools missing/failed). Monitoring disabled.", logging.CRITICAL, exc_info=False)

    logging.info("--- Clipboard Monitor Ended ---")