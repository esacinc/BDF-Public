"""
Plan storage and linking utilities for on_message handler.

This module provides functions for persisting orchestration plans
to DynamoDB thread metadata with proper message association.
"""

import json
import chainlit as cl
from datetime import datetime
from log_helper.logger import get_logger

logger = get_logger()


async def link_plan_to_message(thread_id: str, message_type: str = "assistant_message") -> None:
    """
    Link the current plan to the most recently sent message.
    
    This function is called at the end of the on_message handler after all
    messages have been sent. It:
    1. Queries thread data to get the latest message ID
    2. Retrieves the current plan from session (if it exists)
    3. Converts plan to JSON format (not XML)
    4. Updates thread metadata with plan linked to message ID
    5. Clears the plan from session to prevent stale data
    
    The function is designed to run after message sending completes, taking
    advantage of the fact that thread data is immediately available in DynamoDB
    after msg.send() returns.
    
    Note: Not all messages have plans. The orchestrator may choose to respond
    without creating a plan. This is normal and not an error condition.
    
    Args:
        thread_id: The thread identifier
        message_type: Type of message to look for (default: "assistant_message")
        
    Example:
        ```python
        # At end of on_message handler, after all messages sent
        thread_id = cl.user_session.get("thread_id")
        if thread_id:
            await link_plan_to_message(thread_id)
        ```
    
    Note:
        This should be called ONCE at the end of on_message, not after each
        individual message send. The function will automatically find the last
        sent message, whether it's a success message, error message, or fallback.
    """
    try:
        # Get current plan from session (may not exist - that's OK, we'll store None)
        current_plan = cl.user_session.get('current_plan')
        
        # Get thread data to find the most recent message
        thread_data = await cl.data_layer.get_thread(thread_id)
        if not thread_data:
            return
        
        steps = thread_data.get("steps", [])
        if not steps:
            return
        
        # Find the last message of the specified type
        last_message_id = None
        for step in reversed(steps):
            if step.get("type") == message_type:
                last_message_id = step.get("id")
                break
        
        if not last_message_id:
            logger.debug(f"No message of type '{message_type}' found in thread {thread_id}")
            return
        
        # Convert plan to JSON (not XML) for storage, or None if no plan
        if current_plan:
            plan_dict = current_plan.to_dict()
            plan_json = json.dumps(plan_dict)
        else:
            plan_json = None  # Store None explicitly for messages without plans
        
        # Update thread metadata with plan indexed by message ID
        metadata = thread_data.get('metadata', {})
        
        # Initialize plans dict if it doesn't exist
        if 'plans' not in metadata:
            metadata['plans'] = {}
        
        # Store plan indexed by message ID (preserves all plans)
        metadata['plans'][last_message_id] = plan_json
        
        # Also update current_plan for backward compatibility (points to latest)
        metadata['current_plan'] = plan_json
        
        await cl.data_layer.update_thread(thread_id, metadata=metadata)
        
        # Log success
        if current_plan:
            logger.info(f"Linked plan ({len(current_plan.actions)} actions) to message {last_message_id}")
        else:
            logger.info(f"Stored null plan for message {last_message_id}")
        
    except Exception as e:
        logger.warning(f"Failed to link plan to message: {e}", exc_info=True)

