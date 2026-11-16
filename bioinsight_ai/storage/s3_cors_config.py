"""
S3 CORS Configuration Module

This module handles the CORS (Cross-Origin Resource Sharing) configuration
for S3 buckets used by the application. CORS is required to allow browser-based
clients to access presigned URLs from the S3 bucket.
"""

import boto3
import botocore
from typing import Optional
from log_helper.logger import get_logger

logger = get_logger()


def configure_s3_cors(
    bucket: str,
    region_name: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
    allowed_origins: Optional[list[str]] = None,
) -> bool:
    """
    Configure CORS on an S3 bucket to allow cross-origin requests.
    
    This enables browser-based clients to access presigned URLs from the S3 bucket.
    
    Args:
        bucket: S3 bucket name
        region_name: AWS region name
        aws_access_key_id: AWS access key ID
        aws_secret_access_key: AWS secret access key
        allowed_origins: List of allowed origins. If None, allows all origins (*).
                        For production, specify exact origins like ['https://yourdomain.com']
    
    Returns:
        bool: True if CORS was successfully configured, False otherwise
    """
    
    if allowed_origins is None:
        # Default to allow all origins for development
        # In production, you should specify exact allowed origins
        allowed_origins = ["*"]
    
    cors_config = {
        "CORSRules": [
            {
                "AllowedHeaders": ["*"],
                "AllowedMethods": ["GET", "HEAD"],
                "AllowedOrigins": allowed_origins,
                "ExposeHeaders": ["ETag", "x-amz-meta-custom-header", "Content-Length", "Content-Type"],
                "MaxAgeSeconds": 3000,
            }
        ]
    }
    
    try:
        s3_client = boto3.client(
            "s3",
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        
        s3_client.put_bucket_cors(Bucket=bucket, CORSConfiguration=cors_config)
        logger.info(f"Successfully configured CORS on S3 bucket: {bucket}")
        logger.debug(f"CORS configuration: {cors_config}")
        return True
        
    except botocore.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "NoSuchBucket":
            logger.error(f"S3 bucket '{bucket}' does not exist")
        elif error_code == "AccessDenied":
            logger.error(
                f"Access denied when configuring CORS on bucket '{bucket}'. "
                "Ensure AWS credentials have s3:PutBucketCors permission."
            )
        else:
            logger.error(f"Error configuring CORS on S3 bucket '{bucket}': {e}")
        return False
        
    except Exception as e:
        logger.error(f"Unexpected error configuring CORS on S3 bucket: {e}")
        return False


def verify_s3_cors(
    bucket: str,
    region_name: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
) -> Optional[dict]:
    """
    Verify that CORS is configured on an S3 bucket.
    
    Args:
        bucket: S3 bucket name
        region_name: AWS region name
        aws_access_key_id: AWS access key ID
        aws_secret_access_key: AWS secret access key
    
    Returns:
        dict: CORS configuration if set, None otherwise
    """
    
    try:
        s3_client = boto3.client(
            "s3",
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        
        response = s3_client.get_bucket_cors(Bucket=bucket)
        logger.debug(f"CORS configuration for bucket '{bucket}': {response}")
        return response.get("CORSRules")
        
    except botocore.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "NoSuchCORSConfiguration":
            logger.warning(f"No CORS configuration found on bucket '{bucket}'")
            return None
        else:
            logger.error(f"Error retrieving CORS configuration from S3 bucket '{bucket}': {e}")
            return None
            
    except Exception as e:
        logger.error(f"Unexpected error verifying CORS configuration: {e}")
        return None
