"""
Data models for user feedback collection.

This module defines the core data structures used for storing and managing
user feedback data, including message content, timing information, and
execution plan data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal
import uuid


@dataclass
class MessageData:
    """
    Data structure for storing message content and timing information.
    
    This class captures both user messages and assistant responses along
    with their timestamps for feedback analysis.
    """
    user_message: Optional[str] = None
    assistant_message: Optional[str] = None
    user_message_timestamp: Optional[datetime] = None
    assistant_message_timestamp: Optional[datetime] = None
    response_time: Optional[str] = None  # HH:MM:SS format
    
    def to_dict(self) -> dict:
        """Convert MessageData to dictionary for storage."""
        return {
            'user_message': self.user_message,
            'assistant_message': self.assistant_message,
            'user_message_timestamp': self.user_message_timestamp.isoformat() if self.user_message_timestamp else None,
            'assistant_message_timestamp': self.assistant_message_timestamp.isoformat() if self.assistant_message_timestamp else None,
            'response_time': self.response_time
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MessageData':
        """Create MessageData from dictionary."""
        return cls(
            user_message=data.get('user_message'),
            assistant_message=data.get('assistant_message'),
            user_message_timestamp=datetime.fromisoformat(data['user_message_timestamp']) if data.get('user_message_timestamp') else None,
            assistant_message_timestamp=datetime.fromisoformat(data['assistant_message_timestamp']) if data.get('assistant_message_timestamp') else None,
            response_time=data.get('response_time')
        )


@dataclass
class FeedbackData:
    """
    Comprehensive feedback data structure for storing user feedback information.
    
    This class captures all feedback-related data including the original feedback,
    associated messages, timing information, and execution plan data for analysis.
    """
    # Core feedback information
    feedback_id: str = field(default_factory=lambda: f"fb_{uuid.uuid4().hex[:8]}")
    thread_id: str = ""
    message_id: str = ""
    user_id: str = ""
    rating: Literal[0, 1] = 0  # Binary rating from Chainlit UI: 0=thumbs_down, 1=thumbs_up
    comment: Optional[str] = None
    
    # Message content and timing
    message_data: MessageData = field(default_factory=MessageData)
    
    # Timing information
    feedback_timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Plan information
    serialized_plan: Optional[str] = None
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        """
        Convert FeedbackData to dictionary for DynamoDB storage.
        
        Returns:
            dict: Dictionary representation suitable for DynamoDB storage
        """
        return {
            'feedback_id': self.feedback_id,
            'thread_id': self.thread_id,
            'message_id': self.message_id,
            'user_id': self.user_id,
            'rating': self.rating,
            'comment': self.comment,
            'user_message': self.message_data.user_message,
            'assistant_message': self.message_data.assistant_message,
            'feedback_timestamp': self.feedback_timestamp.isoformat(),
            'user_message_timestamp': self.message_data.user_message_timestamp.isoformat() if self.message_data.user_message_timestamp else None,
            'assistant_message_timestamp': self.message_data.assistant_message_timestamp.isoformat() if self.message_data.assistant_message_timestamp else None,
            'response_time': self.message_data.response_time,
            'serialized_plan': self.serialized_plan,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            # DynamoDB keys for GSI with standard timestamp ordering
            'PK': f"FEEDBACK#{self.feedback_id}",
            'SK': "METADATA",
            'UserFeedbackPK': f"USER#{self.user_id}",
            'UserFeedbackSK': f"FEEDBACK#{self.feedback_timestamp.isoformat()}",
            'ThreadFeedbackPK': f"THREAD#{self.thread_id}",
            'ThreadFeedbackSK': f"FEEDBACK#{self.feedback_timestamp.isoformat()}",
            'TimestampPK': "FEEDBACK",
            'TimestampSK': self.feedback_timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FeedbackData':
        """
        Create FeedbackData from dictionary (e.g., from DynamoDB).
        
        Args:
            data: Dictionary containing feedback data
            
        Returns:
            FeedbackData: Reconstructed feedback data object
        """
        message_data = MessageData(
            user_message=data.get('user_message'),
            assistant_message=data.get('assistant_message'),
            user_message_timestamp=datetime.fromisoformat(data['user_message_timestamp']) if data.get('user_message_timestamp') else None,
            assistant_message_timestamp=datetime.fromisoformat(data['assistant_message_timestamp']) if data.get('assistant_message_timestamp') else None,
            response_time=data.get('response_time')
        )
        
        return cls(
            feedback_id=data['feedback_id'],
            thread_id=data['thread_id'],
            message_id=data['message_id'],
            user_id=data['user_id'],
            rating=data['rating'],
            comment=data.get('comment'),
            message_data=message_data,
            feedback_timestamp=datetime.fromisoformat(data['feedback_timestamp']),
            serialized_plan=data.get('serialized_plan'),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at'])
        )
    
    def validate(self) -> bool:
        """
        Validate that the feedback data contains required fields.
        
        Returns:
            bool: True if all required fields are present and valid
        """
        required_fields = [
            self.feedback_id,
            self.thread_id,
            self.message_id,
            self.user_id
        ]
        
        # Check that all required fields are non-empty strings
        if not all(isinstance(field, str) and field.strip() for field in required_fields):
            return False
        
        # Check that rating is within valid range (0 = thumbs down, 1 = thumbs up)
        if not isinstance(self.rating, int) or self.rating < 0 or self.rating > 1:
            return False
        
        # Check that timestamps are valid datetime objects
        if not isinstance(self.feedback_timestamp, datetime):
            return False
        
        if not isinstance(self.created_at, datetime):
            return False
        
        if not isinstance(self.updated_at, datetime):
            return False
        
        return True
    
    def update_timestamp(self):
        """Update the updated_at timestamp to current time."""
        self.updated_at = datetime.utcnow()