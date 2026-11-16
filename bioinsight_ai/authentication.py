import logging
import chainlit as cl
import os
from typing import Dict, Optional
from chainlit_app import client
from log_helper.logger import get_logger
from datetime import datetime

logger = get_logger()

# Feature toggles
ENABLE_PASSWORD_AUTH = os.getenv("ENABLE_PASSWORD_AUTH", "false").lower() == "false"
ENABLE_OAUTH = os.getenv("ENABLE_OAUTH", "false").lower() == "false"

# DynamoDB table names (via env)
APPROVED_USERS_TABLE = os.getenv("APPROVED_USERS_TABLE")
PENDING_USERS_TABLE = os.getenv("PENDING_USERS_TABLE")

# === DynamoDB Helpers ===
