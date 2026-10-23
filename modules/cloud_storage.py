"""Cloudflare R2 (S3-compatible) storage: archive of finished videos + the SQLite state db.

Credentials come from .env: bucket_endpoint, bucket_name, access_key_id, secret_access_key.
"""
import os
import boto3
import logging
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# where the pipeline state db lives inside the bucket (see modules/state_db.py)
STATE_DB_KEY = "state/reddit_shorts_state.db"

# Global client to save RAM allocation cycles
_r2_client = None

def get_r2_client():
    """Lazily build one shared boto3 S3 client pointed at R2 (region is always 'auto' on R2)."""
    global _r2_client
    if _r2_client is None:
        _r2_client = boto3.client(
            's3',
            endpoint_url=os.getenv("bucket_endpoint"),
            aws_access_key_id=os.getenv("access_key_id"),
            aws_secret_access_key=os.getenv("secret_access_key"),
            config=Config(signature_version='s3v4'),
            region_name='auto'
        )
    return _r2_client

def download_state_db(local_path):
    """Download the state db from R2 to local_path.

    Returns True if downloaded, False if it doesn't exist yet (first ever run -> caller makes a
    fresh db). Any other failure (bad creds, network) is raised on purpose: silently starting an
    empty db would forget every processed post and re-upload duplicates.
    """
    try:
        get_r2_client().download_file(os.getenv("bucket_name"), STATE_DB_KEY, local_path)
        return True
    except ClientError as e:
        # boto3 reports a missing key on download_file as a 404 ClientError
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise

def upload_state_db(local_path):
    """Upload local_path over the state db in R2 (replaces it). Returns True on success."""
    try:
        get_r2_client().upload_file(local_path, os.getenv("bucket_name"), STATE_DB_KEY)
        return True
    except Exception as e:
        logger.error(f"State db upload failed: {e}")
        return False

def archive_video(local_path, post_id, subreddit="unknown"):
    """Uploads the final video to Cloudflare R2 with extra metadata."""
    bucket = os.getenv("bucket_name")
    r2_key = f"archives/{post_id}.mp4"

    if not os.path.exists(local_path):
        logger.error(f"Archive source not found: {local_path}")
        return False

    try:
        s3 = get_r2_client()
        logger.info(f"Uploading {post_id} to R2...")

        # Adding ExtraArgs allows you to tag the file for easier searching later
        s3.upload_file(
            local_path,
            bucket,
            r2_key,
            ExtraArgs={
                'Metadata': {
                    'reddit_id': post_id,
                    'subreddit': subreddit
                }
            }
        )

        logger.info(f"Archived to R2: {r2_key}")
        return True
    except Exception as e:
        logger.error(f"R2 Archive failed: {e}")
        return False
