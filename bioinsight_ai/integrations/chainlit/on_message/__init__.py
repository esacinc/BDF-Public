"""
Plan storage utilities for on_message handler.

This module contains utilities for persisting orchestration plans
to thread metadata with proper message association.
"""

from .plan_storage import link_plan_to_message

__all__ = ['link_plan_to_message']
