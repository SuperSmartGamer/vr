import subprocess
import threading
import time
import logging
import os
import datetime
import sys

# --- Start of embedded logging_setup.py content ---
UNIFIED_LOG_FILE = "thing.txt"
CONSOLE_LOG_FILE = "console.log"

# Custom formatter for .2f seconds in timestamp
class CustomFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ct = datetime.datetime.fromtimestamp(record.created)
        if datefmt:
            s = ct.strftime(datefmt)
        else:
            s = ct.strftime("%Y-%m-%d %H:%M:%S")
        return f"{s}.{int(record.msecs):02d}"

def setup_logging(script_name):
    """Configures logging for a specific script."""
    # Ensure handlers are not duplicated if called multiple times in same process
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Main activity log handler (INFO level to unified_activity_log.txt)
    unified_handler = logging.FileHandler(UNIFIED_LOG_FILE, encoding="utf-8")
    unified_handler.setFormatter(CustomFormatter(fmt='%(asctime)s - %(levelname)s - %(message)s'))
    unified_handler.setLevel(logging.INFO)

    # Console/Error log handler (DEBUG level to console.log, includes tracebacks)
    console_handler = logging.FileHandler(CONSOLE_LOG_FILE, encoding="utf-8")
    console_handler.setFormatter(CustomFormatter(fmt=f'%(asctime)s - {script_name} - %(levelname)s - %(message)s'))
    console_handler.setLevel(logging.DEBUG)

    # Stream handler for console output (INFO level to stdout, no raw tracebacks)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(CustomFormatter(fmt=f'%(asctime)s - {script_name} - %(levelname)s - %(message)s'))
    stream_handler.setLevel(logging.INFO)

    logging.basicConfig(
        level=logging.DEBUG, # Set root logger to lowest level to ensure all messages are caught
        handlers=[unified_handler, console_handler, stream_handler]
    )
# --- End of embedded logging_setup.py content ---

# Setup logging for this script *as early as possible*
setup_logging("WINDOW_MONITOR")
log_write_lock = threading.Lock()

# Platform detection
IS_WINDOWS = sys.platform == 'win32'
IS_LINUX = sys.platform.startswith('linux')


# Attempt imports for window management with error handling
HAS_PYGETWINDOW = False
try:
    import pygetwindow as gw
    HAS_PYGETWINDOW = True
    logging.debug("WINDOW_MONITOR: Successfully imported 'pygetwindow'.")
except ImportError as e:
    logging.critical(f"WINDOW_MONITOR: Failed to import pygetwindow library ({e}). Window title fetching will be disabled.", exc_info=True)


HAS_XDOTOOL = False
HAS_GDBUS = False

# --- Configuration ---
POLLING_INTERVAL_SECONDS = 0.5
# -------------------


# --- Global Variables ---
last_active_window_title = None

# --- Helper to execute shell commands ---
def run_command(command, check_success=True):
    """
    Executes a shell command and returns its stdout.
    Only attempts on Linux.
    """
    if not IS_LINUX: # <-- NEW: Only run commands on Linux
        logging.debug(f"COMMAND_ERROR: Skipping Linux command '{command}' on non-Linux OS.")
        return None
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=check_success, shell=True, timeout=3)
        return result.stdout.strip()
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

# --- Runtime check for CLI tools ---
def check_cli_tools():
    """
    Checks for the presence of necessary command-line window tools.
    Only runs checks on Linux.
    """
    global HAS_XDOTOOL, HAS_GDBUS
    if IS_LINUX: # <-- NEW: Only run checks on Linux
        if run_command("command -v xdotool", check_success=False) is not None:
            HAS_XDOTOOL = True
            logging.debug("WINDOW_MONITOR: 'xdotool' command found.")
        else:
            logging.warning("WINDOW_MONITOR: 'xdotool' command not found. X11 window title fetching may be limited.")

        if run_command("command -v gdbus", check_success=False) is not None:
            HAS_GDBUS = True
            logging.debug("WINDOW_MONITOR: 'gdbus' command found.")
        else:
            logging.warning("WINDOW_MONITOR: 'gdbus' command not found. GNOME Wayland window title fetching may be limited.")
    else:
        logging.debug("WINDOW_MONITOR: Skipping Linux CLI tool checks on non-Linux OS.")


# --- Window Monitoring Functions (Ordered Compatibility) ---

def get_active_window_title_gnome_wayland():
    """
    Attempts to get the active window title on GNOME Wayland via gdbus.
    This method is brittle and GNOME-specific. Only runs on Linux.
    """
    if not IS_LINUX or not HAS_GDBUS: # <-- NEW: Only run on Linux with gdbus
        logging.debug("WINDOW_MONITOR: Skipping GNOME Wayland method (not Linux or gdbus missing).")
        return None

    logging.debug("WINDOW_MONITOR: Attempting Wayland (GNOME) D-Bus method.")
    command = (
        "gdbus call -e -d org.gnome.Shell -o /org/gnome/Shell "
        "-m org.gnome.Shell.Eval "
        "'global.get_window_actors().filter(a=>a.meta_window.has_focus()===true)[0]?.get_meta_window()?.get_title()'"
        " | cut -d\"'\" -f 2"
    )
    title = run_command(command, check_success=False)
    if title:
        logging.debug(f"WINDOW_MONITOR: Got title via GNOME D-Bus: {title}")
    return title

def get_active_window_title_xdotool():
    """
    Attempts to get the active window title via xdotool (X11).
    Only runs on Linux.
    """
    if not IS_LINUX or not HAS_XDOTOOL: # <-- NEW: Only run on Linux with xdotool
        logging.debug("WINDOW_MONITOR: Skipping X11 (xdotool) method (not Linux or xdotool missing).")
        return None

    logging.debug("WINDOW_MONITOR: Attempting X11 (xdotool) method.")
    try:
        window_id = run_command("xdotool getactivewindow", check_success=False)
        if not window_id:
            return None

        title = run_command(f"xdotool getwindowname {window_id}", check_success=False)
        if title:
            logging.debug(f"WINDOW_MONITOR: Got title via xdotool: {title}")
        return title
    except Exception as e:
        logging.debug(f"WINDOW_MONITOR: xdotool method failed: {e}", exc_info=True)
    return None

def get_active_window_title_pygetwindow():
    """
    Attempts to get the active window title via pygetwindow (Cross-platform).
    This will be the primary method on Windows.
    """
    if not HAS_PYGETWINDOW:
        logging.debug("WINDOW_MONITOR: pygetwindow library not available, skipping.")
        return None
    logging.debug("WINDOW_MONITOR: Attempting pygetwindow method.")
    try:
        active_window = None
        try:
            active_window = gw.getActiveWindow()
        except Exception as e:
            # On some systems/environments, getActiveWindow() might raise an error
            # if no active window is truly found or if there are display issues.
            logging.debug(f"WINDOW_MONITOR: pygetwindow.getActiveWindow() failed: {e}", exc_info=True)
            return None

        if active_window and active_window.title:
            logging.debug(f"WINDOW_MONITOR: Got title via pygetwindow: {active_window.title}")
            return active_window.title
    except Exception as e:
        logging.debug(f"WINDOW_MONITOR: Unexpected error with pygetwindow: {e}", exc_info=True)
    return None

def monitor_windows_loop():
    global last_active_window_title
    while True:
        current_title = None

        # 1. Try pygetwindow first (cross-platform, often most reliable)
        if HAS_PYGETWINDOW:
            current_title = get_active_window_title_pygetwindow()

        # 2. If on Linux and pygetwindow didn't yield a title, try Linux-specific methods
        if IS_LINUX and not current_title:
            current_title = get_active_window_title_gnome_wayland()
        if IS_LINUX and not current_title: # Try xdotool if Wayland method also failed
            current_title = get_active_window_title_xdotool()

        if not current_title:
            current_title = "Unknown/No Active Window (All methods failed)"

        if current_title != last_active_window_title:
            with log_write_lock:
                logging.info(f"WINDOW_SWITCH: Focus Changed to: '{current_title}'")
            last_active_window_title = current_title

        time.sleep(POLLING_INTERVAL_SECONDS)

# --- Main Execution Block ---
if __name__ == "__main__":
    logging.info("--- Starting Window Monitor ---")
    logging.info(f"Main activity log: {os.path.abspath(UNIFIED_LOG_FILE)}")
    logging.info(f"Error/Debug log: {os.path.abspath(CONSOLE_LOG_FILE)}")
    logging.info("Press Ctrl+C to stop.")

    if IS_LINUX:
        check_cli_tools() # Check Linux CLI tools only on Linux
        logging.info("WINDOW_MONITOR: Running on Linux. Will attempt various methods for window title.")
    elif IS_WINDOWS:
        logging.info("WINDOW_MONITOR: Running on Windows. Will primarily use pygetwindow.")
    else:
        logging.warning(f"WINDOW_MONITOR: Running on unsupported OS: {sys.platform}. Window monitoring may not work as expected.")


    # Log initial active window
    initial_window = "Unknown/No Active Window (Initial check failed)"
    if HAS_PYGETWINDOW:
        initial_window_attempt = get_active_window_title_pygetwindow()
        if initial_window_attempt:
            initial_window = initial_window_attempt
    
    # If on Linux and pygetwindow didn't get it, try Linux-specific for initial
    if IS_LINUX and initial_window == "Unknown/No Active Window (Initial check failed)":
        initial_window_attempt = get_active_window_title_gnome_wayland()
        if initial_window_attempt:
            initial_window = initial_window_attempt
        else:
            initial_window_attempt = get_active_window_title_xdotool()
            if initial_window_attempt:
                initial_window = initial_window_attempt

    last_active_window_title = initial_window
    logging.info(f"WINDOW_SWITCH: Initial Active Window: '{initial_window}'")

    # Determine if any monitoring method is available
    if not HAS_PYGETWINDOW and ((IS_LINUX and not (HAS_GDBUS or HAS_XDOTOOL)) or IS_WINDOWS):
        # On Windows, pygetwindow is the main option. If it's missing, we're stuck.
        # On Linux, if pygetwindow is missing AND no CLI tools are found, we're stuck.
        logging.critical("WINDOW_MONITOR: No suitable window monitoring method available. Monitoring disabled.")
        sys.exit(1)

    try:
        monitor_windows_loop()
    except KeyboardInterrupt:
        logging.info("WINDOW_MONITOR: KeyboardInterrupt detected. Stopping window monitoring.")
    except Exception as e:
        logging.critical(f"WINDOW_MONITOR: A critical error occurred in window monitoring loop: {e}", exc_info=True)
    finally:
        logging.info("--- Window Monitor Ended ---")