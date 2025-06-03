# main_monitor.py
import psutil # Needed for type hints if adding dummy data, otherwise not directly used for collection
import sqlite3
import time
import os
import sys
import csv
import subprocess
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# --- Configuration ---
# SQLite Database settings
DB_FILE = "monitoring_data.db"
TABLE_NAME = "system_metrics"

# Path to the secondary data collection script (kg.py)
SECONDARY_SCRIPT_PATH = "kg.py"

# Local file that kg.py writes to, and this script reads/clears.
LOCAL_LOG_FILE = "thing.txt"

# --- Global variable to store the secondary process PID ---
# We'll store the PID in a temporary file to persist it between runs of main_monitor.py
PID_FILE = "secondary_script_pid.txt"

# --- Email Configuration (IMPORTANT: Set these for email functionality) ---
# It's highly recommended to use environment variables for sensitive info like passwords.
EMAIL_SENDER_ADDRESS = os.environ.get("EMAIL_SENDER_ADDRESS", "wetwwilman100@gmail.com")
EMAIL_SENDER_PASSWORD = os.environ.get("EMAIL_SENDER_PASSWORD", "WilliamBoydNzive07!")
EMAIL_RECEIVER_ADDRESS = os.environ.get("EMAIL_RECEIVER_ADDRESS", "wetwilman100@gmail.com")
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))

# Ensure the directory for the local log file and PID file exists
# This assumes main_monitor.py runs from the directory where thing.txt and pid file should be
os.makedirs(os.path.dirname(os.path.abspath(LOCAL_LOG_FILE)), exist_ok=True)
os.makedirs(os.path.dirname(os.path.abspath(PID_FILE)), exist_ok=True)


def initialize_db():
    """
    Connects to the SQLite database and creates the table if it doesn't exist.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    # Ensure this schema matches the order of data written by kg.py and parsed below
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            timestamp INTEGER,
            computer_id TEXT,
            cpu_percent REAL,
            memory_percent REAL,
            disk_usage_root_percent REAL,
            network_bytes_sent INTEGER,
            network_bytes_recv INTEGER
        )
    ''')
    conn.commit()
    conn.close()
    print(f"Database '{DB_FILE}' initialized and table '{TABLE_NAME}' ensured.")

def get_secondary_script_pid():
    """Reads the PID of the secondary script from a file."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                return int(f.read().strip())
        except (ValueError, IOError):
            return None
    return None

def set_secondary_script_pid(pid):
    """Writes the PID of the secondary script to a file."""
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(pid))
    except IOError as e:
        print(f"Error writing PID to file: {e}")

def clear_secondary_script_pid():
    """Removes the PID file."""
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except OSError as e:
            print(f"Error removing PID file: {e}")

def is_process_running(pid):
    """Checks if a process with the given PID is currently running."""
    if pid is None:
        return False
    try:
        # On Unix-like systems, os.kill(pid, 0) checks if PID exists without sending a signal
        # On Windows, this will raise OSError if process doesn't exist.
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def start_secondary_script_if_needed():
    """
    Starts the secondary data collection script if it's not already running.
    """
    current_pid = get_secondary_script_pid()
    
    if current_pid and is_process_running(current_pid):
        print(f"Secondary script '{SECONDARY_SCRIPT_PATH}' already running with PID: {current_pid}")
        return # Already running, nothing to do

    print(f"Secondary script '{SECONDARY_SCRIPT_PATH}' not running or PID file invalid. Attempting to start...")
    try:
        process = subprocess.Popen(
            [sys.executable, SECONDARY_SCRIPT_PATH],
            stdout=subprocess.DEVNULL,  # Redirect stdout to /dev/null
            stderr=subprocess.DEVNULL,  # Redirect stderr to /dev/null
            close_fds=True # Close file descriptors in child process
        )
        set_secondary_script_pid(process.pid)
        print(f"Secondary script '{SECONDARY_SCRIPT_PATH}' launched with PID: {process.pid}")
        # Give it a moment to initialize
        time.sleep(2) 
    except FileNotFoundError:
        print(f"Error: Secondary script '{SECONDARY_SCRIPT_PATH}' not found. Check path.")
        clear_secondary_script_pid() # Clear PID file if script not found
    except Exception as e:
        print(f"Error starting secondary script '{SECONDARY_SCRIPT_PATH}': {e}")
        clear_secondary_script_pid() # Clear PID file on other errors

def process_and_save_local_file_to_db(file_path):
    """
    Reads data from the local text file, parses each line, and inserts into SQLite.
    """
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        print(f"Local log file '{file_path}' is empty or does not exist, skipping database insertion.")
        return True # Nothing to process, consider it successful

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    inserted_count = 0

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                parts = line.split(',')
                # IMPORTANT: Ensure this matches the order in kg.py's get_system_metrics_as_text()
                if len(parts) != 7: # timestamp, computer_id, cpu, mem, disk, net_sent, net_recv
                    print(f"Warning: Skipping line {line_num} in '{file_path}' due to incorrect number of fields: '{line}'")
                    continue

                try:
                    metrics = (
                        int(parts[0]),      # timestamp
                        parts[1],           # computer_id (text)
                        float(parts[2]),    # cpu_percent
                        float(parts[3]),    # memory_percent
                        float(parts[4]),    # disk_usage_root_percent
                        int(parts[5]),      # network_bytes_sent
                        int(parts[6])       # network_bytes_recv
                    )
                    cursor.execute(f'''
                        INSERT INTO {TABLE_NAME} (
                            timestamp, computer_id, cpu_percent, memory_percent,
                            disk_usage_root_percent, network_bytes_sent, network_bytes_recv
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', metrics)
                    inserted_count += 1
                except ValueError as ve:
                    print(f"Error parsing data on line {line_num} in '{file_path}': '{line}' - {ve}. Skipping line.")
                except Exception as e:
                    print(f"An unexpected error occurred processing line {line_num} in '{file_path}': {e}. Skipping line.")
        
        conn.commit()
        print(f"Successfully processed and inserted {inserted_count} records from '{file_path}' into '{DB_FILE}'.")
        return True

    except Exception as e:
        print(f"Error reading or processing local log file '{file_path}': {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def clear_local_log_file(file_path):
    """Clears the content of the local log file."""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'w', encoding='utf-8') as f:
                f.truncate(0) # Truncate file to 0 bytes
            print(f"Local log file '{file_path}' cleared.")
        else:
            print(f"Cannot clear '{file_path}': file does not exist.")
    except Exception as e:
        print(f"Error clearing local log file '{file_path}': {e}")

def export_metrics_to_csv(output_file="exported_metrics.csv", start_time=None, end_time=None):
    """
    Exports system metrics from the SQLite database to a CSV file.
    
    Args:
        output_file (str): The name of the CSV file to create.
        start_time (int, optional): Unix timestamp to start exporting data from.
        end_time (int, optional): Unix timestamp to end exporting data at.
    Returns:
        str: The path to the created CSV file if successful, None otherwise.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        query = f"SELECT * FROM {TABLE_NAME}"
        params = []
        
        if start_time is not None and end_time is not None:
            query += " WHERE timestamp BETWEEN ? AND ?"
            params.append(start_time)
            params.append(end_time)
        elif start_time is not None:
            query += " WHERE timestamp >= ?"
            params.append(start_time)
        elif end_time is not None:
            query += " WHERE timestamp <= ?"
            params.append(end_time)
            
        query += " ORDER BY timestamp ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        column_names = [description[0] for description in cursor.description]

        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(column_names)
            csv_writer.writerows(rows)

        print(f"Successfully exported {len(rows)} records to '{output_file}'")
        return output_file

    except Exception as e:
        print(f"Error exporting data to CSV: {e}")
        return None
    finally:
        conn.close()

def send_email_with_attachment(subject, body, attachment_path):
    """
    Sends an email with a specified subject, body, and attachment.
    Requires EMAIL_SENDER_ADDRESS, EMAIL_SENDER_PASSWORD, EMAIL_RECEIVER_ADDRESS,
    SMTP_SERVER, and SMTP_PORT to be configured.
    """
    if not all([EMAIL_SENDER_ADDRESS, EMAIL_SENDER_PASSWORD, EMAIL_RECEIVER_ADDRESS, SMTP_SERVER, SMTP_PORT]):
        print("Email configuration incomplete. Cannot send email.")
        print("Please set email environment variables or directly in the script.")
        return False

    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER_ADDRESS
    msg['To'] = EMAIL_RECEIVER_ADDRESS
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    if attachment_path and os.path.exists(attachment_path):
        try:
            with open(attachment_path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f"attachment; filename= {os.path.basename(attachment_path)}",
            )
            msg.attach(part)
            print(f"Attached file: {attachment_path}")
        except Exception as e:
            print(f"Error attaching file {attachment_path}: {e}")
            return False
    else:
        print(f"Attachment file not found or path is empty: {attachment_path}")
        return False

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER_ADDRESS, EMAIL_SENDER_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_SENDER_ADDRESS, EMAIL_RECEIVER_ADDRESS, text)
        server.quit()
        print(f"Email with attachment '{os.path.basename(attachment_path)}' sent successfully to {EMAIL_RECEIVER_ADDRESS}.")
        return True
    except smtplib.SMTPAuthenticationError:
        print("SMTP Authentication Error: Check your email address and password/app password.")
        print("For Gmail, you might need an 'App password' if you have 2-Factor Authentication enabled.")
        return False
    except smtplib.SMTPConnectError:
        print(f"SMTP Connection Error: Could not connect to SMTP server {SMTP_SERVER}:{SMTP_PORT}.")
        print("Check server address, port, and network connectivity.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred while sending email: {e}")
        return False


if __name__ == "__main__":
    print("Main monitoring script (orchestrator) started.")
    
    # Initialize the database
    initialize_db()

    # 1. Ensure the secondary script (kg.py) is running
    start_secondary_script_if_needed()

    # Check for export/email arguments first
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'export':
        output_filename = "exported_metrics.csv"
        print(f"Running in export mode. Exporting data to '{output_filename}'...")
        exported_file = export_metrics_to_csv(output_filename)
        
        if len(sys.argv) > 2 and sys.argv[2].lower() == 'email' and exported_file:
            print(f"Attempting to email '{exported_file}'...")
            subject = f"System Monitoring Report - {time.strftime('%Y-%m-%d %H:%M:%S')}"
            body = f"Please find attached the latest system monitoring data from your monitoring system."
            if send_email_with_attachment(subject, body, exported_file):
                print("Email sent successfully.")
            else:
                print("Failed to send email.")
            # Optionally, delete the CSV file after sending email
            # os.remove(exported_file)
        elif len(sys.argv) > 2 and sys.argv[2].lower() == 'email' and not exported_file:
            print("Cannot email: CSV export failed.")
        
        sys.exit(0) # Exit after export/email operations

    # 2. Process data from LOCAL_LOG_FILE (thing.txt) and save to DB
    if process_and_save_local_file_to_db(LOCAL_LOG_FILE):
        # 3. Clear LOCAL_LOG_FILE after successful processing
        clear_local_log_file(LOCAL_LOG_FILE) 
    else:
        print("Failed to process and save file content to DB. Data will remain in local file for next attempt.")
    
    print("Main monitoring script (orchestrator) finished.")
    # The script will now exit
