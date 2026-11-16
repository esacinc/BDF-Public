#!/usr/bin/env python3
"""
Script to create the DynamoDB feedback table with the correct schema.

This script creates the feedback_table_dev table with the proper primary key
and Global Secondary Indexes (GSIs) as specified in the design document.
"""

import boto3
import sys
import os
from botocore.exceptions import ClientError

# When run directly (not imported), we need to set up the path
if __name__ == "__main__":
    # Add the bioinsight_ai directory to path for config imports
    bioinsight_ai_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    if bioinsight_ai_dir not in sys.path:
        sys.path.insert(0, bioinsight_ai_dir)

try:
    from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, FEEDBACK_TABLE
except ImportError as e:
    print(f"Error importing config: {e}")
    print("Make sure you're running this from the bioinsight_ai directory or that config.py is accessible")
    sys.exit(1)

def create_feedback_table():
    """Create the DynamoDB feedback table with proper schema."""
    
    # Initialize DynamoDB client
    dynamodb = boto3.client(
        'dynamodb',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )
    
    table_name = FEEDBACK_TABLE
    print(f"Creating DynamoDB table: {table_name}")
    
    try:
        # Create table with primary key and GSIs
        response = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {
                    'AttributeName': 'PK',
                    'KeyType': 'HASH'  # Partition key
                },
                {
                    'AttributeName': 'SK',
                    'KeyType': 'RANGE'  # Sort key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'PK',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'SK',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'UserFeedbackPK',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'UserFeedbackSK',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'ThreadFeedbackPK',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'ThreadFeedbackSK',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'TimestampPK',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'TimestampSK',
                    'AttributeType': 'S'
                }
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'UserFeedbackIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'UserFeedbackPK',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'UserFeedbackSK',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                },
                {
                    'IndexName': 'ThreadFeedbackIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'ThreadFeedbackPK',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'ThreadFeedbackSK',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                },
                {
                    'IndexName': 'TimestampIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'TimestampPK',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'TimestampSK',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                }
            ],
            BillingMode='PAY_PER_REQUEST',  # On-demand pricing
            Tags=[
                {
                    'Key': 'Environment',
                    'Value': 'dev'
                },
                {
                    'Key': 'Purpose',
                    'Value': 'feedback-collection'
                },
                {
                    'Key': 'Application',
                    'Value': 'bioinsight-ai'
                }
            ]
        )
        
        print(f"✅ Table creation initiated successfully!")
        print(f"Table ARN: {response['TableDescription']['TableArn']}")
        print(f"Table Status: {response['TableDescription']['TableStatus']}")
        print("\n⏳ Waiting for table to become active...")
        
        # Wait for table to become active
        waiter = dynamodb.get_waiter('table_exists')
        waiter.wait(
            TableName=table_name,
            WaiterConfig={
                'Delay': 5,
                'MaxAttempts': 60
            }
        )
        
        # Verify table is active
        table_info = dynamodb.describe_table(TableName=table_name)
        status = table_info['Table']['TableStatus']
        
        if status == 'ACTIVE':
            print(f"✅ Table {table_name} is now ACTIVE and ready to use!")
            print(f"📊 Table details:")
            print(f"   - Item Count: {table_info['Table']['ItemCount']}")
            print(f"   - Size: {table_info['Table']['TableSizeBytes']} bytes")
            print(f"   - GSI Count: {len(table_info['Table'].get('GlobalSecondaryIndexes', []))}")
            return True
        else:
            print(f"⚠️ Table status: {status}")
            return False
            
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceInUseException':
            print(f"✅ Table {table_name} already exists!")
            return True
        else:
            print(f"❌ Error creating table: {e}")
            return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    """Main function to create the feedback table."""
    print("🚀 DynamoDB Feedback Table Creation Script")
    print("=" * 50)
    
    # Validate configuration
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        print("❌ AWS credentials not found in environment variables")
        sys.exit(1)
    
    if not AWS_REGION:
        print("❌ AWS_REGION not found in environment variables")
        sys.exit(1)
    
    if not FEEDBACK_TABLE:
        print("❌ FEEDBACK_TABLE not found in environment variables")
        sys.exit(1)
    
    print(f"📋 Configuration:")
    print(f"   - Region: {AWS_REGION}")
    print(f"   - Table Name: {FEEDBACK_TABLE}")
    print()
    
    # Create the table
    success = create_feedback_table()
    
    if success:
        print("\n🎉 Feedback table setup completed successfully!")
        print("You can now restart the Chainlit application.")
    else:
        print("\n❌ Failed to create feedback table.")
        sys.exit(1)

if __name__ == "__main__":
    main()