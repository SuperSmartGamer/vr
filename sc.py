import socket
import mss
import mss.tools
import time
import io
import zlib
import threading

# --- Configuration ---
RECEIVER_TAILSCALE_IP = '100.96.244.18' # Your PC's Tailscale IP
RECEIVER_PORT = 12345
FPS = 1 # Frames per second (set to 1 or 2 for a video-like experience)
JPEG_QUALITY = 50 # JPEG quality (0-100), lower means smaller file and faster transfer

# Calculate delay for desired FPS
DELAY_TIME = 1 / FPS

def send_screen_data():
    """
    Connects to the receiver and continuously sends screen capture data.
    Attempts to reconnect if the connection is lost.
    """
    while True: # Loop to attempt reconnection if connection drops
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            print(f"Attempting to connect to receiver at {RECEIVER_TAILSCALE_IP}:{RECEIVER_PORT}...")
            client_socket.connect((RECEIVER_TAILSCALE_IP, RECEIVER_PORT))
            print(f"Successfully connected to receiver.")
        except socket.error as e:
            print(f"Failed to connect to receiver: {e}. Retrying in 5 seconds...")
            client_socket.close()
            time.sleep(5)
            continue # Try connecting again

        with mss.mss() as sct:
            # Capture the primary monitor (sct.monitors[1]).
            # Adjust to sct.monitors[0] for all screens, or other index for specific monitor.
            monitor = sct.monitors[1] 

            print(f"Starting screen capture at {FPS} FPS with JPEG quality {JPEG_QUALITY}...")
            try:
                while True:
                    start_time = time.time()
                    
                    # Capture the screen
                    sct_img = sct.grab(monitor)
                    
                    # Convert to PIL Image format for JPEG compression
                    img_pil = mss.tools.to_pil_image(sct_img)

                    # Convert PIL Image to JPEG bytes
                    img_byte_arr = io.BytesIO()
                    img_pil.save(img_byte_arr, format='JPEG', quality=JPEG_QUALITY)
                    jpeg_bytes = img_byte_arr.getvalue()

                    # Compress with zlib on top of JPEG. This can further reduce size, especially for static screens.
                    compressed_data = zlib.compress(jpeg_bytes)

                    # Send the size of the compressed data first (4 bytes)
                    data_size = len(compressed_data)
                    client_socket.sendall(data_size.to_bytes(4, 'big'))

                    # Send the actual compressed data
                    client_socket.sendall(compressed_data)

                    # Control frame rate
                    end_time = time.time()
                    elapsed_time = end_time - start_time
                    if elapsed_time < DELAY_TIME:
                        time.sleep(DELAY_TIME - elapsed_time)

            except mss.exception.ScreenShotError as e:
                print(f"Screenshot failed: {e}. Screen might be locked or no active session. Trying again...")
                time.sleep(1) # Small pause before next capture attempt
            except socket.error as e:
                print(f"Socket error during send: {e}. Connection likely lost. Attempting to reconnect...")
                client_socket.close()
                time.sleep(2) # Wait a bit before trying to reconnect
                break # Break inner loop to trigger outer reconnection loop
            except Exception as e:
                print(f"An unexpected error occurred during sending: {e}")
                client_socket.close()
                time.sleep(2)
                break # Break inner loop to trigger outer reconnection loop

if __name__ == "__main__":
    send_screen_data()