"""
Data Layer Manager for Chainlit application.

This module manages initialization and configuration of data layers following
Chainlit best practices, supporting both conversation and feedback data layers.
"""

import boto3
import chainlit as cl
import chainlit.data as cl_data
from botocore.exceptions import ClientError
from chainlit.data.dynamodb import DynamoDBDataLayer
from chainlit.data.storage_clients.s3 import S3StorageClient

from .feedback_data_layer import FeedbackDataLayer
from log_helper.logger import get_logger

logger = get_logger()


class DataLayerManager:
    """
    Manages initialization and configuration of data layers following Chainlit best practices.
    
    This class handles setup of both conversation data layer (for chat history) and
    feedback data layer (for feedback storage) with proper configuration and error handling.
    """
    
    def __init__(self, conversation_table: str, feedback_table: str, client: boto3.client, storage_provider=None):
        """
        Initialize data layer manager with table names and AWS client.
        
        Args:
            conversation_table: Name of the DynamoDB table for conversation data
            feedback_table: Name of the DynamoDB table for feedback data
            client: Boto3 DynamoDB client
            storage_provider: S3 storage provider for file attachments
        """
        self.conversation_table = conversation_table
        self.feedback_table = feedback_table
        self.client = client
        self.storage_provider = storage_provider
        
        # Initialize data layers
        self._conversation_layer = None
        self._feedback_layer = None
    
    def _validate_table(self, table_name: str) -> None:
        """
        Validate that a DynamoDB table exists and is active.
        
        This method checks if the specified table exists and is in an ACTIVE state.
        It provides consistent validation for both conversation and feedback tables.
        
        Args:
            table_name: Name of the DynamoDB table to validate
            
        Raises:
            ValueError: If the table does not exist or is not in an ACTIVE state
        """
        try:
            response = self.client.describe_table(TableName=table_name)
            table_status = response['Table']['TableStatus']
            
            if table_status != 'ACTIVE':
                error_msg = f"Table '{table_name}' exists but is not ACTIVE (current status: {table_status})"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            
            # Log AWS configuration from client for debugging
            client_region = self.client.meta.region_name
            credentials = self.client._request_signer._credentials
            access_key = credentials.access_key if credentials else None
            key_status = "Present" if access_key else "Missing"
            logger.error(f"AWS Configuration - Region: {client_region}, Access Key ID: {key_status}")
            
            if error_code == 'ResourceNotFoundException':
                error_msg = f"Table '{table_name}' does not exist"
                logger.error(error_msg)
                raise ValueError(error_msg) from e
            else:
                error_msg = f"Failed to validate table '{table_name}': {error_code} - {str(e)}"
                logger.error(error_msg)
                raise ValueError(error_msg) from e
        except Exception as e:
            # Log AWS configuration from client for debugging
            client_region = self.client.meta.region_name
            credentials = self.client._request_signer._credentials
            access_key = credentials.access_key if credentials else None
            key_status = "Present" if access_key else "Missing"
            logger.error(f"AWS Configuration - Region: {client_region}, Access Key ID: {key_status}")
            error_msg = f"Unexpected error validating table '{table_name}': {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e
    
    def setup_conversation_layer(self) -> DynamoDBDataLayer:
        """
        Set up the conversation data layer for chat history.
        
        This creates and configures the DynamoDB data layer for storing
        conversation history and thread data.
        
        Returns:
            DynamoDBDataLayer: Configured conversation data layer
            
        Raises:
            ValueError: If the conversation table does not exist or is not ACTIVE
        """
        if self._conversation_layer is None:
            try:
                # Validate table exists and is ACTIVE before creating layer
                self._validate_table(self.conversation_table)
                
                self._conversation_layer = DynamoDBDataLayer(
                    table_name=self.conversation_table,
                    client=self.client,
                    storage_provider=self.storage_provider
                )
            except Exception as e:
                logger.error(f"Failed to create conversation data layer: {e}")
                raise
        
        return self._conversation_layer
    
    def setup_feedback_layer(self) -> FeedbackDataLayer:
        """
        Set up the feedback data layer for feedback storage.
        
        This creates and configures the custom feedback data layer for storing
        comprehensive feedback information.
        
        Returns:
            FeedbackDataLayer: Configured feedback data layer
            
        Raises:
            ValueError: If the feedback table does not exist or is not ACTIVE
        """
        if self._feedback_layer is None:
            try:
                # Validate table exists and is ACTIVE before creating layer
                self._validate_table(self.feedback_table)
                
                self._feedback_layer = FeedbackDataLayer(
                    table_name=self.feedback_table,
                    client=self.client
                )
            except Exception as e:
                logger.error(f"Failed to create feedback data layer: {e}")
                raise
        
        return self._feedback_layer
    
    def configure_chainlit_layers(self):
        """
        Configure Chainlit to use the data layers.
        
        This method sets up both the legacy and modern data layer references
        to ensure backward compatibility while following current best practices.
        """
        try:
            # Set up conversation layer for Chainlit
            conversation_layer = self.setup_conversation_layer()
            
            # Configure Chainlit data layer (both legacy and modern approaches)
            cl_data._data_layer = conversation_layer  # Legacy support
            cl.data_layer = conversation_layer        # Modern approach
            
        except Exception as e:
            logger.error(f"Failed to configure Chainlit data layers: {e}")
            raise
    
    def get_conversation_layer(self) -> DynamoDBDataLayer:
        """
        Get the conversation data layer instance.
        
        Returns:
            DynamoDBDataLayer: The conversation data layer
            
        Raises:
            RuntimeError: If conversation layer hasn't been set up
        """
        if self._conversation_layer is None:
            raise RuntimeError("Conversation data layer not initialized. Call setup_conversation_layer() first.")
        return self._conversation_layer
    
    def get_feedback_layer(self) -> FeedbackDataLayer:
        """
        Get the feedback data layer instance.
        
        Returns:
            FeedbackDataLayer: The feedback data layer
            
        Raises:
            RuntimeError: If feedback layer hasn't been set up
        """
        if self._feedback_layer is None:
            raise RuntimeError("Feedback data layer not initialized. Call setup_feedback_layer() first.")
        return self._feedback_layer
    
    def validate_configuration(self):
        """
        Validate that all data layers are properly configured.
        
        This method checks that both conversation and feedback data layers
        are accessible and properly configured.
        
        Raises:
            RuntimeError: If any data layer is not properly configured
        """
        validation_errors = []
        
        try:
            # Validate conversation layer
            conversation_layer = self.get_conversation_layer()
            
            # Test conversation layer connectivity
            if not hasattr(conversation_layer, 'table_name'):
                validation_errors.append("Conversation layer missing table_name attribute")
            elif not conversation_layer.table_name:
                validation_errors.append("Conversation layer table_name is empty")
            
            logger.info("✅ Conversation data layer validation passed")
            
        except Exception as e:
            validation_errors.append(f"Conversation layer validation failed: {e}")
        
        try:
            # Validate feedback layer
            feedback_layer = self.get_feedback_layer()
            
            # Test feedback layer connectivity
            if not hasattr(feedback_layer, 'table_name'):
                validation_errors.append("Feedback layer missing table_name attribute")
            elif not feedback_layer.table_name:
                validation_errors.append("Feedback layer table_name is empty")
            
            logger.info("✅ Feedback data layer validation passed")
            
        except Exception as e:
            validation_errors.append(f"Feedback layer validation failed: {e}")
        
        # Validate AWS client
        if not self.client:
            validation_errors.append("AWS DynamoDB client is not configured")
        
        # Report validation results
        if validation_errors:
            error_msg = f"❌ Data layer configuration validation failed: {'; '.join(validation_errors)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        logger.info("✅ All data layers validated successfully")