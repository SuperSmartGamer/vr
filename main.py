import threading
import subprocess
import time
import sys

# Install requirements.txt
subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

scripts = ["kg.py"]

def repeat_function():
    while True:
        print("Repeating task")
        time.sleep(60)

def run_script(script):
    subprocess.Popen([sys.executable, script])

for s in scripts:
    threading.Thread(target=run_script, args=(s,), daemon=True).start()

threading.Thread(target=repeat_function, daemon=True).start()

while True:
    time.sleep(1)
