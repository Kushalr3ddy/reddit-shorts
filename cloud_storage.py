import os
import boto3
import logging
from botocore.client import Config
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def get_r2_client():
    return boto3.client(
        's3',
        endpoint_url=os.getenv("bucket_endpoint"),
        aws_access_key_id=os.getenv("access_key_id"),
        aws_secret_access_key=os.getenv("secret_access_key"),
        config=Config(signature_version='s3v4'),
        region_name='auto'
    )

def archive_video(local_path, post_id):
    """Uploads the final video to Cloudflare R2."""
    bucket = os.getenv("bucket_name")
    r2_key = f"archives/{post_id}.mp4"
    
    try:
        s3 = get_r2_client()
        logger.info(f"Uploading {post_id} to R2...")
        s3.upload_file(local_path, bucket, r2_key)
        logger.info(f"✅ Archived to R2: {r2_key}")
        return True
    except Exception as e:
        logger.error(f"R2 Archive failed: {e}")
        return False