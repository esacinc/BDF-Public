"""
Helper functions for processing user feedback submissions.

This module contains helper functions for feedback collection and processing
that can be called from the main chainlit app feedback handler.
"""

import uuid
from datetime import datetime
from typing import Optional
import chainlit as cl
from chainlit.types import Feedback
from chainlit.data.base import BaseDataLayer

from .data_models import FeedbackData, MessageData
from .data_collector import FeedbackDataCollector
from .feedback_data_layer import FeedbackDataLayer
from .retry_utils import retry_with_exponential_backoff
from log_helper.logger import get_logger

logger = get_logger()


async def process_feedback(feedback: Feedback, feedback_layer: FeedbackDataLayer, conversation_layer: BaseDataLayer) -> bool:
    """
    Process feedback within the constraints of the feedback context.
    
    This function works without access to cl.user_session and collects only
    the data that's available in the feedback context scope.
    
    Args:
        feedback: Chainlit feedback object containing user rating and comment
        feedback_layer: FeedbackDataLayer instance for storing feedback data
        conversation_layer: Chainlit data layer for accessing conversation data
        
    Returns:
        bool: True if feedback was processed successfully, False otherwise
    """
    logger.info(f"Processing feedback: {feedback.forId} with rating {feedback.value}")
    
    try:
        # Validate feedback data layer
        if not feedback_layer:
            logger.error("No feedback data layer provided")
            return False
        
        # Collect feedback data
        feedback_data = await collect_feedback_data(feedback, conversation_layer)
        
        # Store feedback data with retry logic
        feedback_id = await _store_feedback_with_retry(feedback_layer, feedback_data)
        
        if feedback_id:
            logger.info(f"Feedback stored successfully with ID: {feedback_id}")
            return True
        else:
            logger.warning(f"Failed to store feedback for message {feedback.forId}")
            return False
        
    except Exception as e:
        # Log error without exposing sensitive information
        sanitized_error = _sanitize_error_message(str(e))
        logger.error(f"Error processing feedback for message {feedback.forId}: {sanitized_error}")
        
        # Attempt graceful degradation - store minimal feedback data
        try:
            await _store_minimal_feedback(feedback)
            logger.info(f"Stored minimal feedback data for message {feedback.forId}")
            return True
        except Exception as fallback_error:
            logger.error(f"Failed to store even minimal feedback: {_sanitize_error_message(str(fallback_error))}")
            return False


async def collect_feedback_data(feedback: Feedback, conversation_layer: BaseDataLayer) -> FeedbackData:
    """
    Collect feedback data without access to cl.user_session.
    
    This function works within the constraints of the feedback context and
    only collects data that's available without session access.
    
    Args:
        feedback: Chainlit feedback object
        conversation_layer: Chainlit data layer for accessing conversation data
        
    Returns:
        FeedbackData: Feedback data object with available information
    """
    try:
        # Initialize data collector
        collector = FeedbackDataCollector(conversation_layer)
        
        # Create basic feedback data from available information
        feedback_data = FeedbackData(
            thread_id=feedback.threadId or "",
            message_id=feedback.forId or "",
            user_id="",  # Will be extracted using collector method
            rating=feedback.value if feedback.value is not None else 0,  # Binary: 0=thumbs down, 1=thumbs up
            comment=feedback.comment,
            feedback_timestamp=datetime.utcnow()
        )
        
        # Extract message data if thread and message IDs are available
        try:
            if feedback.threadId and feedback.forId:
                message_data = await collector.extract_message_data(feedback.threadId, feedback.forId)
                feedback_data.message_data = message_data
            else:
                logger.warning("Missing thread ID or message ID, skipping message data extraction")
                feedback_data.message_data = MessageData()
        except Exception as e:
            logger.warning(f"Failed to extract message data, using empty MessageData: {e}")
            feedback_data.message_data = MessageData()
        
        # Extract user ID using collector method
        if feedback.threadId:
            feedback_data.user_id = await collector.extract_user_id(feedback.threadId)
        
        # Extract orchestration plan using collector method (with message ID for correct association)
        if feedback.threadId:
            feedback_data.serialized_plan = await collector.extract_orchestration_plan(
                feedback.threadId,
                feedback.forId  # Pass message_id to get message-specific plan
            )
        else:
            feedback_data.serialized_plan = None
            logger.warning("No thread_id available, cannot extract plan")
        
        return feedback_data
        
    except Exception as e:
        logger.warning(f"Error collecting feedback data: {str(e)}")
        
        # Fallback to minimal feedback data
        feedback_data = FeedbackData(
            feedback_id=str(uuid.uuid4()),
            thread_id=feedback.threadId or "",
            message_id=feedback.forId or "",
            user_id="anonymous",  # Fallback when thread data unavailable
            rating=feedback.value if feedback.value is not None else 0,  # Binary: 0=thumbs down, 1=thumbs up
            comment=feedback.comment,
            feedback_timestamp=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        logger.info(f"Using fallback feedback data for message {feedback.forId}")
        return feedback_data


# Helper functions for error handling and graceful degradation

async def _store_feedback_with_retry(feedback_layer: FeedbackDataLayer, feedback_data: FeedbackData) -> Optional[str]:
    """Store feedback data with retry logic handled by the data layer."""
    try:
        feedback_id = await feedback_layer.store_feedback(feedback_data)
        return feedback_id
    except Exception as e:
        logger.warning(f"Failed to store feedback: {str(e)}")
        raise


async def _store_minimal_feedback(feedback: Feedback) -> None:
    """Store minimal feedback data as fallback."""
    logger.info(f"Storing minimal feedback for message {feedback.forId}")
    
    # Create minimal feedback record
    minimal_data = {
        'feedback_id': str(uuid.uuid4()),
        'message_id': feedback.forId or "",
        'thread_id': feedback.threadId or "",
        'rating': feedback.value if feedback.value is not None else 0,
        'comment': feedback.comment or "",
        'timestamp': datetime.utcnow().isoformat(),
        'fallback': True
    }
    
    # Log the minimal data (this serves as a backup record)
    logger.info(f"Minimal feedback data: {minimal_data}")
    
    # In a production system, this could write to a fallback storage system
    # For now, logging serves as the backup mechanism


def _sanitize_error_message(error_msg: str) -> str:
    """Sanitize error messages to remove sensitive information."""
    # Remove potential sensitive patterns
    import re
    
    # Remove AWS credentials patterns
    sanitized = re.sub(r'aws_access_key_id=[^&\s]+', 'aws_access_key_id=***', error_msg)
    sanitized = re.sub(r'aws_secret_access_key=[^&\s]+', 'aws_secret_access_key=***', sanitized)
    
    # Remove potential user data patterns
    sanitized = re.sub(r'user_id=[^&\s]+', 'user_id=***', sanitized)
    sanitized = re.sub(r'email=[^&\s]+', 'email=***', sanitized)
    
    # Truncate very long error messages
    if len(sanitized) > 500:
        sanitized = sanitized[:500] + "... (truncated)"
    
    return sanitized
