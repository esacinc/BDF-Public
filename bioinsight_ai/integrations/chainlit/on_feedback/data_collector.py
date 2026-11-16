"""
Feedback data collector for gathering comprehensive feedback information.

This module orchestrates the collection of all feedback-related data from various
sources, including thread data, message content, timing information, and execution plans.
"""

from typing import Optional
from datetime import datetime

import chainlit as cl
from chainlit.data.base import BaseDataLayer

from .data_models import FeedbackData, MessageData
from log_helper.logger import get_logger

logger = get_logger()


class FeedbackDataCollector:
    """
    Orchestrates the collection of all feedback-related data from various sources.
    
    This class is responsible for gathering message content, timing information,
    and execution plan data to create comprehensive feedback records.
    """
    
    def __init__(self, conversation_layer: Optional[BaseDataLayer] = None):
        """
        Initialize with conversation data layer for thread access.
        
        Args:
            conversation_layer: DynamoDB data layer for accessing conversation data
        """
        self.conversation_layer = conversation_layer
    
    def _map_run_to_assistant_message(self, steps: list, message_id: str) -> str:
        """
        Map a run step ID to its corresponding assistant_message step ID.
        
        If the message_id is a run step, this finds the next assistant_message step.
        If it's already an assistant_message (or other type), returns the ID unchanged.
        
        Args:
            steps: List of steps from thread data
            message_id: The original message ID (could be run or assistant_message)
            
        Returns:
            str: The assistant_message ID (mapped from run if needed, or original ID)
        """
        for i, step in enumerate(steps):
            if step.get("id") == message_id:
                step_type = step.get("type")
                
                if step_type == "run":
                    # This is a run step, find the following assistant_message
                    for j in range(i + 1, len(steps)):
                        next_step = steps[j]
                        if next_step.get("type") == "assistant_message":
                            mapped_id = next_step.get("id")
                            logger.debug(f"Mapped run step {message_id} → assistant_message {mapped_id}")
                            return mapped_id
                    
                    # No assistant_message found after run step
                    logger.warning(f"No assistant_message found after run step {message_id}")
                    return message_id
                else:
                    # Already the correct type, return as-is
                    return message_id
        
        # Message ID not found in steps
        logger.warning(f"Message ID {message_id} not found in steps")
        return message_id
    
    async def extract_message_data(self, thread_id: str, message_id: str) -> MessageData:
        """
        Extract user and assistant messages with timing.
        
        This method implements graceful degradation - it will return partial
        message data even if some information is missing or inaccessible.
        
        Args:
            thread_id: Thread identifier
            message_id: Message identifier
            
        Returns:
            MessageData: Message content and timing information (may be partial)
        """
        message_data = MessageData()
        
        try:
            if not self.conversation_layer:
                logger.warning("No conversation layer available for message extraction")
                return message_data
            
            # Get thread data from conversation layer with error handling
            thread_data = None
            try:
                thread_data = await self.conversation_layer.get_thread(thread_id)
            except Exception as e:
                logger.warning(f"Failed to retrieve thread data for {thread_id}: {e}")
                return message_data
            
            if not thread_data:
                logger.warning(f"No thread data found for thread {thread_id}")
                return message_data
            
            # Extract messages from thread steps with graceful handling
            steps = thread_data.get("steps", [])
            if not steps:
                logger.warning(f"No steps found in thread {thread_id}")
                return message_data
            
            # Find the target message and its context
            target_message_index = None
            for i, step in enumerate(steps):
                if step.get("id") == message_id:
                    target_message_index = i
                    break
            
            if target_message_index is None:
                logger.warning(f"Message {message_id} not found in thread {thread_id}")
                return message_data
            
            # Extract assistant message (the target message) with error handling
            try:
                target_step = steps[target_message_index]
                step_type = target_step.get("type")
                
                if step_type == "assistant_message":
                    # Direct assistant message
                    message_data.assistant_message = target_step.get("output", "")
                    end_time = target_step.get("end")
                    if end_time:
                        try:
                            message_data.assistant_message_timestamp = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                        except Exception as e:
                            logger.warning(f"Failed to parse assistant message timestamp: {e}")
                            
                elif step_type == "run":
                    # The target is a run step, look for the assistant message that follows it
                    logger.debug(f"Target message is a 'run' step, looking for corresponding assistant message")
                    
                    # Look for the next assistant_message step after this run
                    for i in range(target_message_index + 1, len(steps)):
                        step = steps[i]
                        if step.get("type") == "assistant_message":
                            message_data.assistant_message = step.get("output", "")
                            end_time = step.get("end")
                            if end_time:
                                try:
                                    message_data.assistant_message_timestamp = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                                except Exception as e:
                                    logger.warning(f"Failed to parse assistant message timestamp: {e}")
                            logger.debug(f"Found assistant message following run step: {step.get('id')}")
                            break
                    else:
                        logger.warning(f"No assistant message found after run step {message_id}")
                        
                else:
                    logger.warning(f"Target message type '{step_type}' is not assistant_message or run")
                    
            except Exception as e:
                logger.warning(f"Failed to extract assistant message: {e}")
            
            # Find the preceding user message with error handling
            try:
                for i in range(target_message_index - 1, -1, -1):
                    step = steps[i]
                    if step.get("type") == "user_message":
                        message_data.user_message = step.get("output", "")
                        # Extract timestamp from start
                        start_time = step.get("start")
                        if start_time:
                            try:
                                message_data.user_message_timestamp = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                            except Exception as e:
                                logger.warning(f"Failed to parse user message timestamp: {e}")
                        break
            except Exception as e:
                logger.warning(f"Failed to extract user message: {e}")
            
            # Calculate response time if both timestamps are available
            if message_data.user_message_timestamp and message_data.assistant_message_timestamp:
                try:
                    time_diff = message_data.assistant_message_timestamp - message_data.user_message_timestamp
                    total_seconds = int(time_diff.total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    message_data.response_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                except Exception as e:
                    logger.warning(f"Failed to calculate response time: {e}")
                    message_data.response_time = None
            
        except Exception as e:
            logger.error(f"Unexpected error extracting message data: {e}")
        
        return message_data
    
    async def extract_orchestration_plan(self, thread_id: str, message_id: str = None) -> Optional[str]:
        """
        Extract orchestration plan for a specific message.
        
        Args:
            thread_id: Thread identifier
            message_id: Message identifier (can be run step or assistant_message step)
            
        Returns:
            Optional[str]: Serialized plan JSON or None if no plan exists
        """
        try:
            if not self.conversation_layer:
                logger.warning("No conversation layer available for plan extraction")
                return None
            
            thread_data = await self.conversation_layer.get_thread(thread_id)
            if not thread_data:
                logger.warning(f"No thread data found for thread {thread_id}")
                return None
            
            # Extract plan from thread metadata
            metadata = thread_data.get('metadata', {})
            
            # Message ID should ALWAYS be provided
            if message_id:
                # Map run step to assistant_message step if needed
                steps = thread_data.get("steps", [])
                assistant_message_id = self._map_run_to_assistant_message(steps, message_id)
                
                # Look up plan using the assistant_message ID
                plans = metadata.get('plans', {})
                if assistant_message_id in plans:
                    return plans[assistant_message_id]
                else:
                    logger.error(f"Message ID {assistant_message_id} NOT found in plans dictionary.")
                    return None
            else:
                logger.error(f"No message_id provided to extract_orchestration_plan.")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to extract orchestration plan from thread {thread_id}: {e}")
            return None
    
    async def extract_user_id(self, thread_id: str) -> str:
        """
        Extract user ID from thread data.
        
        Args:
            thread_id: Thread identifier
            
        Returns:
            str: User ID or empty string if not found
        """
        try:
            if not self.conversation_layer:
                logger.warning("No conversation layer available for user ID extraction")
                return ""
            
            thread_data = await self.conversation_layer.get_thread(thread_id)
            if not thread_data:
                logger.warning(f"No thread data found for thread {thread_id}")
                return ""
            
            # Extract user ID from thread data (not metadata)
            user_id = thread_data.get("userId", "")
            if user_id:
                return user_id
            else:
                logger.warning("No user ID found in thread data")
                return ""
                
        except Exception as e:
            logger.warning(f"Failed to extract user ID from thread {thread_id}: {e}")
            return ""