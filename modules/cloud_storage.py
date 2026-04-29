import os
import boto3
import logging
from botocore.client import Config
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Global client to save RAM allocation cycles
_r2_client = None

def get_r2_client():
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