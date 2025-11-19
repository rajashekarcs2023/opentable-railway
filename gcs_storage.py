"""
GCS Storage utility for uploading media files
Returns public URLs that work in ASI One
Drop-in replacement for s3_storage.py using Google Cloud Storage

Supports multiple authentication methods:
1. Base64-encoded credentials (for Agentverse): GCS_CREDENTIALS_BASE64
2. JSON file path (local dev): GOOGLE_APPLICATION_CREDENTIALS
3. Application Default Credentials (local dev): gcloud auth application-default login
"""

import os
import base64
import json
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from google.cloud import storage
from google.oauth2 import service_account

load_dotenv()

# GCS Configuration
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
GOOGLE_CLOUD_PROJECT = os.getenv('GOOGLE_CLOUD_PROJECT')
GCS_CREDENTIALS_BASE64 = os.getenv('GCS_CREDENTIALS_BASE64')

# Initialize GCS client
gcs_client = None
gcs_bucket = None

if GCS_BUCKET_NAME and GOOGLE_CLOUD_PROJECT:
    try:
        # Method 1: Base64-encoded credentials (for Agentverse)
        if GCS_CREDENTIALS_BASE64:
            print("Using base64-encoded GCS credentials (Agentverse mode)")
            creds_json = base64.b64decode(GCS_CREDENTIALS_BASE64).decode('utf-8')
            credentials = service_account.Credentials.from_service_account_info(
                json.loads(creds_json)
            )
            gcs_client = storage.Client(credentials=credentials, project=GOOGLE_CLOUD_PROJECT)
        else:
            # Method 2 & 3: JSON file or ADC (for local development)
            print("Using default GCS credentials (local dev mode)")
            gcs_client = storage.Client(project=GOOGLE_CLOUD_PROJECT)
        
        gcs_bucket = gcs_client.bucket(GCS_BUCKET_NAME)
        print(f"✅ GCS initialized: bucket={GCS_BUCKET_NAME}, project={GOOGLE_CLOUD_PROJECT}")
    except Exception as e:
        print(f"❌ Failed to initialize GCS client: {e}")
        gcs_client = None
        gcs_bucket = None


def upload_to_storage(file_data: bytes, filename: str, content_type: str = 'video/mp4') -> str:
    """
    Upload file to GCS and return public URL
    
    Args:
        file_data: File bytes to upload
        filename: Name for the file (should be unique)
        content_type: MIME type (default: video/mp4)
    
    Returns:
        Public URL to the uploaded file
    """
    
    if not gcs_client or not gcs_bucket:
        raise ValueError("GCS not configured. Add GCS_BUCKET_NAME and GOOGLE_CLOUD_PROJECT to .env")
    
    # Upload to videos/ folder
    gcs_key = f"videos/{filename}"
    
    # Create blob and upload
    blob = gcs_bucket.blob(gcs_key)
    blob.upload_from_string(file_data, content_type=content_type)
    
    # Note: If you have uniform bucket-level access enabled, 
    # you need to set bucket-level IAM permissions once:
    # gsutil iam ch allUsers:objectViewer gs://asione
    
    # Return public URL (works if bucket has public access via IAM)
    public_url = blob.public_url
    
    return public_url


def is_storage_configured() -> bool:
    """
    Check if GCS is properly configured
    """
    return gcs_client is not None and gcs_bucket is not None


# Backward compatibility aliases for S3 migration
upload_to_s3 = upload_to_storage
is_s3_configured = is_storage_configured
upload_to_gcs = upload_to_storage
is_gcs_configured = is_storage_configured
