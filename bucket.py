import boto3
import os
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client(
    service_name='s3',
    # Provide your R2 endpoint: https://<ACCOUNT_ID>.r2.cloudflarestorage.com
    endpoint_url=os.environ.get("bucket_endpoint"),
    # Provide your R2 Access Key ID and Secret Access Key
    aws_access_key_id=os.environ.get("access_key_id"),
    aws_secret_access_key=os.environ.get("secret_access_key"),
    region_name='auto',  # Required by boto3, not used by R2
)

# Upload a file
#local bucket_name bucket_location
s3.upload_file('test.txt', os.environ.get("bucket_name"), 'test.txt')
print('Uploaded test.txt')

# Download a file
s3.download_file(os.environ.get("bucket_name"), 'test.txt', 'downloaded.txt')
print('Downloaded to downloaded.txt')

# List objects
response = s3.list_objects_v2(Bucket=os.environ.get("bucket_name"))
for obj in response.get('Contents', []):
    print(f"Object: {obj['Key']}")