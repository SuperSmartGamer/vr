import requests
import time

def send_discord_message(webhook_url, message):
    try:
        # Discord webhook expects a JSON payload with a "content" key
        payload = {"content": message}
        response = requests.post(webhook_url, json=payload)
        if response.status_code in (200, 204):
            print(f"Message sent successfully at {time.ctime()}: {message}")
        else:
            print(f"Failed to send message. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")

def main():
    # Configuration
    c = "https://discord.com/api/webhooks/1391088430557171742/AowKxTSMVmOk_"
    WEBHOOK_URL = f"{c}cOkq8bESNEoTmjsPbKw4LdjbHzBF0Ptufg291AxkzgdOO2PUhwtKEBo"
    message = "Hello, this is a test message!"  # Customize your message

    print("Starting Discord webhook message sender...")
    while True:
        send_discord_message(WEBHOOK_URL, message)
        time.sleep(60)  # Wait 1 minute (60 seconds) before next send

if __name__ == "__main__":
    main()