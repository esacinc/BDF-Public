"""
Feedback data layer for DynamoDB operations.

This module provides a custom data layer implementation specifically for feedback
operations, including storage, retrieval, and querying of feedback data.
"""

from typing import Optional, List
import os
import boto3
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer
from botocore.exceptions import ClientError
from datetime import datetime

from .data_models import FeedbackData
from .retry_utils import retry_with_exponential_backoff, dynamodb_circuit_breaker
from log_helper.logger import get_logger

logger = get_logger()


class FeedbackDataLayer:
    """
    Custom data layer implementation specifically for feedback operations.
    
    This class handles all DynamoDB operations for feedback data including
    storage, retrieval, and querying with appropriate error handling.
    """
    
    def __init__(self, table_name: str, client: boto3.client):
        """
        Initialize feedback data layer with DynamoDB configuration.
        
        Args:
            table_name: Name of the DynamoDB table for feedback storage
            client: Boto3 DynamoDB client
        """
        self.table_name = table_name
        self.client = client
        
        # Initialize type serializers for DynamoDB operations
        self.serializer = TypeSerializer()
        self.deserializer = TypeDeserializer()
    
    @retry_with_exponential_backoff(max_attempts=3, base_delay=1.0, max_delay=10.0)
    @dynamodb_circuit_breaker
    async def store_feedback(self, feedback_data: FeedbackData) -> str:
        """
        Store comprehensive feedback data and return feedback ID.
        
        This method implements graceful degradation - it will attempt to store
        feedback even if some validation fails, prioritizing core feedback capture.
        
        Args:
            feedback_data: Complete feedback data to store
            
        Returns:
            str: Feedback ID of the stored record
            
        Raises:
            ValueError: If core feedback data is invalid
            ClientError: If DynamoDB operation fails after retries
        """
        # Validate core feedback data (graceful validation)
        try:
            if not feedback_data.validate():
                # Try to fix common validation issues
                if not feedback_data.thread_id:
                    feedback_data.thread_id = "unknown"
                    logger.warning("Missing thread_id, using 'unknown'")
                
                if not feedback_data.message_id:
                    feedback_data.message_id = "unknown"
                    logger.warning("Missing message_id, using 'unknown'")
                
                if not feedback_data.user_id:
                    feedback_data.user_id = "anonymous"
                    logger.warning("Missing user_id, using 'anonymous'")
                
                if feedback_data.rating is None or feedback_data.rating < 0 or feedback_data.rating > 1:
                    feedback_data.rating = 0  # Default to thumbs down
                    logger.warning("Invalid rating, using default value 0 (thumbs down)")
                
                # Re-validate after fixes
                if not feedback_data.validate():
                    raise ValueError("Core feedback data is invalid even after graceful fixes")
        except Exception as e:
            logger.error(f"Validation failed for feedback data: {e}")
            raise ValueError(f"Invalid feedback data: {e}")
        
        # Update timestamp before storing
        feedback_data.update_timestamp()
        
        try:
            # Convert to DynamoDB item format with error handling
            try:
                item = feedback_data.to_dict()
                # Ensure null Plan values are explicitly handled
                if item.get('serialized_plan') is None:
                    logger.debug("Storing null value for plan data")
            except Exception as e:
                logger.error(f"Failed to convert feedback data to dict: {e}")
                # Try to create a minimal item with core data
                item = {
                    'PK': f"FEEDBACK#{feedback_data.feedback_id}",
                    'SK': 'METADATA',
                    'feedback_id': feedback_data.feedback_id,
                    'thread_id': feedback_data.thread_id,
                    'message_id': feedback_data.message_id,
                    'user_id': feedback_data.user_id,
                    'rating': feedback_data.rating,
                    'comment': feedback_data.comment or "",
                    'feedback_timestamp': feedback_data.feedback_timestamp.isoformat(),
                    'serialized_plan': feedback_data.serialized_plan,  # Ensure null Plan is stored
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat(),
                }
                
                # Add GSI keys with standard timestamp ordering
                item.update({
                    'UserFeedbackPK': f"USER#{feedback_data.user_id}",
                    'UserFeedbackSK': f"FEEDBACK#{feedback_data.feedback_timestamp.isoformat()}",
                    'ThreadFeedbackPK': f"THREAD#{feedback_data.thread_id}",
                    'ThreadFeedbackSK': f"FEEDBACK#{feedback_data.feedback_timestamp.isoformat()}",
                    'TimestampPK': "FEEDBACK",
                    'TimestampSK': feedback_data.feedback_timestamp.isoformat()
                })
                logger.warning("Using minimal item structure due to conversion error")
                if item.get('serialized_plan') is None:
                    logger.debug("Storing null value for plan data in minimal item")
            
            # Serialize item for DynamoDB client
            # Handle None values explicitly (TypeSerializer doesn't support None)
            serialized_item = {}
            for k, v in item.items():
                if v is None:
                    serialized_item[k] = {'NULL': True}  # DynamoDB NULL type
                else:
                    serialized_item[k] = self.serializer.serialize(v)
            
            # Store in DynamoDB using client
            response = self.client.put_item(
                TableName=self.table_name,
                Item=serialized_item
            )
            
            logger.info(f"Successfully stored feedback: {feedback_data.feedback_id}")
            return feedback_data.feedback_id
            
        except ClientError as e:
            logger.error(f"Failed to store feedback {feedback_data.feedback_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error storing feedback {feedback_data.feedback_id}: {e}")
            raise ClientError(
                error_response={'Error': {'Code': 'InternalError', 'Message': str(e)}},
                operation_name='PutItem'
            )
    
    @retry_with_exponential_backoff(max_attempts=2, base_delay=0.5, max_delay=5.0)
    @dynamodb_circuit_breaker
    async def get_feedback(self, feedback_id: str) -> Optional[FeedbackData]:
        """
        Retrieve feedback data by ID.
        
        Args:
            feedback_id: Unique feedback identifier
            
        Returns:
            Optional[FeedbackData]: Feedback data if found, None otherwise
        """
        try:
            # Serialize key for DynamoDB client
            key = {
                'PK': self.serializer.serialize(f"FEEDBACK#{feedback_id}"),
                'SK': self.serializer.serialize('METADATA')
            }
            
            response = self.client.get_item(
                TableName=self.table_name,
                Key=key
            )
            
            if 'Item' not in response:
                logger.info(f"Feedback not found: {feedback_id}")
                return None
            
            # Deserialize DynamoDB item
            item = {k: self.deserializer.deserialize(v) for k, v in response['Item'].items()}
            
            # Convert to FeedbackData
            feedback_data = FeedbackData.from_dict(item)
            logger.info(f"Retrieved feedback: {feedback_id}")
            return feedback_data
            
        except ClientError as e:
            logger.error(f"Failed to retrieve feedback {feedback_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving feedback {feedback_id}: {e}")
            return None
    
    @retry_with_exponential_backoff(max_attempts=2, base_delay=0.5, max_delay=5.0)
    @dynamodb_circuit_breaker
    async def list_feedback_by_user(self, user_id: str, limit: int = 50) -> List[FeedbackData]:
        """
        List feedback submissions by user using GSI.
        
        Args:
            user_id: User identifier
            limit: Maximum number of records to return
            
        Returns:
            List[FeedbackData]: List of feedback records for the user
        """
        try:
            response = self.client.query(
                TableName=self.table_name,
                IndexName='UserFeedbackIndex',
                KeyConditionExpression='UserFeedbackPK = :pk',
                ExpressionAttributeValues={
                    ':pk': self.serializer.serialize(f"USER#{user_id}")
                },
                Limit=limit,
                ScanIndexForward=False  # Most recent first
            )
            
            feedback_list = []
            for dynamodb_item in response.get('Items', []):
                try:
                    # Deserialize DynamoDB item
                    item = {k: self.deserializer.deserialize(v) for k, v in dynamodb_item.items()}
                    feedback_data = FeedbackData.from_dict(item)
                    feedback_list.append(feedback_data)
                except Exception as e:
                    logger.warning(f"Failed to parse feedback item for user {user_id}: {e}")
                    continue
            
            logger.info(f"Retrieved {len(feedback_list)} feedback records for user: {user_id}")
            return feedback_list
            
        except ClientError as e:
            logger.error(f"Failed to list feedback for user {user_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing feedback for user {user_id}: {e}")
            return []
    
    @retry_with_exponential_backoff(max_attempts=2, base_delay=0.5, max_delay=5.0)
    @dynamodb_circuit_breaker
    async def list_feedback_by_thread(self, thread_id: str) -> List[FeedbackData]:
        """
        List all feedback for a conversation thread using GSI.
        
        Args:
            thread_id: Thread identifier
            
        Returns:
            List[FeedbackData]: List of feedback records for the thread
        """
        try:
            response = self.client.query(
                TableName=self.table_name,
                IndexName='ThreadFeedbackIndex',
                KeyConditionExpression='ThreadFeedbackPK = :pk',
                ExpressionAttributeValues={
                    ':pk': self.serializer.serialize(f"THREAD#{thread_id}")
                },
                ScanIndexForward=False  # Most recent first
            )
            
            feedback_list = []
            for dynamodb_item in response.get('Items', []):
                try:
                    # Deserialize DynamoDB item
                    item = {k: self.deserializer.deserialize(v) for k, v in dynamodb_item.items()}
                    feedback_data = FeedbackData.from_dict(item)
                    feedback_list.append(feedback_data)
                except Exception as e:
                    logger.warning(f"Failed to parse feedback item for thread {thread_id}: {e}")
                    continue
            
            logger.info(f"Retrieved {len(feedback_list)} feedback records for thread: {thread_id}")
            return feedback_list
            
        except ClientError as e:
            logger.error(f"Failed to list feedback for thread {thread_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing feedback for thread {thread_id}: {e}")
            return []
    
    def get_table_name_from_env(self) -> str:
        """
        Get feedback table name from environment variable.
        
        Returns:
            str: Table name from FEEDBACK_TABLE environment variable
            
        Raises:
            ValueError: If FEEDBACK_TABLE environment variable is not set
        """
        table_name = os.getenv('FEEDBACK_TABLE')
        if not table_name:
            raise ValueError("FEEDBACK_TABLE environment variable is not set")
        return table_name