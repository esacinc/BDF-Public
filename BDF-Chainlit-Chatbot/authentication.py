import logging
import chainlit as cl
import os
from typing import Dict, Optional

# Configure logging to output to stdout
logging.basicConfig(
    level=logging.INFO,  # Log level
    format="%(asctime)s - %(levelname)s - %(message)s"  # Log format
)
logger = logging.getLogger(__name__)

ENABLE_PASSWORD_AUTH = os.getenv("ENABLE_PASSWORD_AUTH", "false").lower() == "true"
ENABLE_OAUTH = os.getenv("ENABLE_OAUTH", "false").lower() == "true"

if ENABLE_PASSWORD_AUTH:
    @cl.password_auth_callback
    def auth_callback(username: str, password: str):
        # Fetch the user matching username from your database
        # and compare the hashed password with the value stored in the database
        if (username, password) == ("", ""):
            return cl.User(
                identifier="admin", metadata={"role": "admin", "provider": "credentials"}
            )   
        else:
            return None

if ENABLE_OAUTH:
    @cl.oauth_callback
    def oauth_callback(
        provider_id: str,
        token: str,
        raw_user_data: Dict[str, str],
        default_user: cl.User,
    ) -> Optional[cl.User]:
        if provider_id == 'google' and 'email' in raw_user_data:
            user_email = raw_user_data['email']
            logger.info(f"User email: {user_email}")  # Log the email to stdout
            if user_email.endswith('icf@gmail.com'):
                return default_user
            else:
                logger.warning(f"Unauthorized email attempted login: {user_email}")
                return None
        else:
            logger.error("OAuth callback triggered with invalid provider or missing email.")
            return None
