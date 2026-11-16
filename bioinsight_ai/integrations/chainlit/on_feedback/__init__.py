"""
User feedback collection module for BioInsight AI.

This module provides comprehensive feedback collection functionality including:
- Data models for feedback and message data
- Feedback data collection and storage
- Helper functions for processing feedback
"""

import sys
import os

# Add the bioinsight_ai directory to path for config imports
# This allows all modules in this package to use: from config import ...
_bioinsight_ai_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _bioinsight_ai_dir not in sys.path:
    sys.path.insert(0, _bioinsight_ai_dir)

from .data_models import FeedbackData, MessageData
from .feedback_handler import (
    process_feedback,
    collect_feedback_data
)

__all__ = [
    'FeedbackData', 
    'MessageData', 
    'process_feedback',
    'collect_feedback_data'
]