import os
import pickle
import logging
import random
import time
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Scopes required for uploading
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def get_authenticated_service():
    """Authenticates the user and returns the YouTube service object."""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired YouTube token...")
            creds.refresh(Request())
        else:
            logger.info("No valid token found. Opening browser for login...")
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('youtube', 'v3', credentials=creds)

def resumable_upload(insert_request):
    """Handles the actual upload with exponential backoff for retries."""
    response = None
    error = None
    retry = 0
    max_retries = 10

    while response is None:
        try:
            logger.info("Uploading chunk...")
            status, response = insert_request.next_chunk()
            if response is not None:
                if 'id' in response:
                    logger.info(f"✅ Success! Video ID: {response['id']}")
                    return response['id']
                else:
                    exit(f"Unexpected response: {response}")
            if status:
                logger.info(f"Progress: {int(status.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                error = f"Retriable HTTP error {e.resp.status}"
            else:
                raise e
        except Exception as e:
            error = f"Retriable error: {e}"

        if error:
            logger.warning(error)
            retry += 1
            if retry > max_retries:
                exit("Max retries exceeded.")
            sleep_seconds = random.random() * (2 ** retry)
            logger.info(f"Sleeping {sleep_seconds:.2f}s before retry...")
            time.sleep(sleep_seconds)

def start_upload(file_path, title, description):
    """Initializes the upload request."""
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return

    youtube = get_authenticated_service()
    
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['#shorts', '#reddit', '#automation'],
            'categoryId': '24' # Entertainment
        },
        'status': {
            'privacyStatus': 'private', # Start as private for safety
            'selfDeclaredMadeForKids': False
        }
    }

    # Use chunksize=-1 for a single resumable session (simpler for most files)
    media = MediaFileUpload(file_path, mimetype='video/mp4', chunksize=-1, resumable=True)
    
    request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=media
    )
    
    return resumable_upload(request)

if __name__ == '__main__':
    # --- TEST BLOCK ---
    # Replace these with an actual path/title on your laptop to test
    TEST_FILE = "temp/test_video.mp4" 
    TEST_TITLE = "Automated Reddit Short Test"
    TEST_DESC = "Testing the YouTube Data API v3 upload script.\n\n#shorts"

    if os.path.exists(TEST_FILE):
        start_upload(TEST_FILE, TEST_TITLE, TEST_DESC)
    else:
        logger.warning(f"Test file {TEST_FILE} not found. Drop an mp4 there to run the main test.")