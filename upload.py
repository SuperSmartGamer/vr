import boto3
from botocore.client import Config
import os
from datetime import datetime
import logging # <-- NEW: Import logging module

# === ENTER YOUR INFO HERE ===
ACCESS_KEY = 'db8efca097d2506714901db06ea81b97'
SECRET_KEY = '4a873df3ad2fdd9be894f779461fb2ab9def4202ea50afc42e9ecf029498d0fa'
ACCOUNT_ID = 'fd5b99900fc2700f1f893f9ee5d52c07'   # Found in the R2 endpoint URL
BUCKET_NAME="my-bucket"
# =============================

# Get a logger instance for upload.py. This will integrate with
# clipboard_monitor.py's logging setup because they share handlers.
logger = logging.getLogger("UPLOAD_SCRIPT")

def upload_to_r2(FILE_PATH):
    now = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = os.path.basename(FILE_PATH)
    name, ext = os.path.splitext(filename)
    new_filename = f"{name}_{now}{ext}"

    endpoint = f'https://{ACCOUNT_ID}.r2.cloudflarestorage.com'

    logger.info(f'UPLOAD: Attempting to upload {os.path.basename(FILE_PATH)} as {new_filename} to R2 bucket "{BUCKET_NAME}" at {endpoint}')

    try:
        s3 = boto3.client('s3',
            endpoint_url=endpoint,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            config=Config(signature_version='s3v4'),
            region_name='auto'
        )

        with open(FILE_PATH, 'rb') as f:
            s3.upload_fileobj(f, BUCKET_NAME, new_filename)

        final_url = f'https://{ACCOUNT_ID}.r2.cloudflarestorage.com/{BUCKET_NAME}/{new_filename}'
        logger.info(f'UPLOAD: Successfully uploaded {new_filename}. Accessible at: {final_url}')
        print(f'Uploaded as: {final_url}') # Keep the print for immediate feedback in terminal
        return True # <-- IMPORTANT: Return True on success!
    except Exception as e:
        logger.error(f"UPLOAD: Failed to upload {new_filename} to R2. Error: {e}", exc_info=True)
        return False # <-- IMPORTANT: Return False on failure!

