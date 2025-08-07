import logging
import chainlit as cl
import os
from typing import Dict, Optional
from chainlit_app import client
from log_helper.logger import get_logger
from datetime import datetime

logger = get_logger()

# Feature toggles
ENABLE_PASSWORD_AUTH = os.getenv("ENABLE_PASSWORD_AUTH", "false").lower() == "true"
ENABLE_OAUTH = os.getenv("ENABLE_OAUTH", "false").lower() == "true"

# DynamoDB table names (via env)
APPROVED_USERS_TABLE = os.getenv("APPROVED_USERS_TABLE")
PENDING_USERS_TABLE = os.getenv("PENDING_USERS_TABLE")

# === DynamoDB Helpers ===

def is_email_approved(email: str) -> bool:
    try:
        response = client.get_item(
            TableName=APPROVED_USERS_TABLE,
            Key={"user_email": {"S": email}}
        )
        return "Item" in response
    except Exception as e:
        logger.exception(f"Error checking approved email in DynamoDB: {e}")
        return False

def save_pending_email(email: str, reason: Optional[str] = None):
    try:
        client.put_item(
            TableName=PENDING_USERS_TABLE,
            Item={
                "user_email": {"S": email},
                "reason": {"S": reason or "N/A"},
                "timestamp": {"S": datetime.utcnow().isoformat()}
            }
        )
        logger.info(f"Saved access request for {email}")
    except Exception as e:
        logger.exception(f"Error saving pending request: {e}")

# === Password Auth ===
if ENABLE_PASSWORD_AUTH:
    @cl.password_auth_callback
    def auth_callback(username: str, password: str):
        if (username, password) == ("", ""):
            return cl.User(
                identifier="admin", metadata={"role": "admin", "provider": "credentials"}
            )
        else:
            return None

# === OAuth Auth ===
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
            logger.info(f"OAuth login attempt from: {user_email}")

            if is_email_approved(user_email):
                logger.info(f"Approved user: {user_email}")
                return default_user
            else:
                #logger.warning(f"Unapproved user. Adding to PendingUsers: {user_email}")
                #save_pending_email(user_email)

                #logger.info(f"User {user_email} added to pending users. Login denied with notice.")
                #return None
            
                logger.info(f"User not approved. Adding to ApprovedUsers: {user_email}")
                try:
                    client.put_item(
                        TableName=APPROVED_USERS_TABLE,
                        Item={
                            "user_email": {"S": user_email},
                            "timestamp": {"S": datetime.utcnow().isoformat()}
                        }
                    )
                    logger.info(f"User {user_email} added to ApprovedUsers")
                except Exception as e:
                    logger.exception(f"Failed to add user to ApprovedUsers: {e}")
                    return None

                return default_user            

        else:
            logger.error("OAuth callback triggered with invalid provider or missing email.")
            return None