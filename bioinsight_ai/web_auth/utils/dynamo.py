# /web_auth/utils/dynamo.py
import boto3
from config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    APPROVED_USERS_TABLE,
    PENDING_USERS_TABLE,
)

from log_helper.logger import get_logger
logger = get_logger()

dynamodb = boto3.client(
    "dynamodb",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)


def get_user(email: str):
    try:
        resp = dynamodb.get_item(
            TableName=APPROVED_USERS_TABLE,
            Key={"user_email": {"S": email}},
        )
        return resp.get("Item")
    except Exception as e:
        logger.error(f"Failed to get user '{email}' from DynamoDB")
        # Extract AWS configuration from dynamodb client
        client_region = dynamodb.meta.region_name
        credentials = dynamodb._request_signer._credentials
        access_key = credentials.access_key if credentials else None
        key_status = "Present" if access_key else "Missing"
        logger.error(f"AWS Configuration - Region: {client_region}, Access Key ID: {key_status}")
        logger.error(f"Error: {str(e)}")
        raise


def save_pending_user(
    full_name: str,
    email: str,
    organization: str,
    job_title: str,
    additional_info: str = "",
    auth_provider: str = "password"
):
    """
    Save a new user into the pending_users table.
    - For password-based signup: auth_provider="password"
    - For Google OAuth signup: auth_provider="google"
    """

    item = {
        "user_email": {"S": email},
        "full_name": {"S": full_name},
        "organization": {"S": organization},
        "job_title": {"S": job_title},
        "additional_info": {"S": additional_info},
        "auth_provider": {"S": auth_provider},
        "status": {"S": "pending"},
    }

    dynamodb.put_item(
        TableName=PENDING_USERS_TABLE,
        Item=item
    )

    logger.info(f"Pending user saved: {email} (provider={auth_provider})")
    return item


def get_pending_users():
    try:
        resp = dynamodb.scan(
            TableName=PENDING_USERS_TABLE,
            FilterExpression="#st = :pending",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":pending": {"S": "pending"}},
        )
        return resp.get("Items", [])
    except Exception as e:
        logger.error(f"Error scanning pending users: {e}")
        raise

def approve_user(
    email: str,
    hashed_password: str | None,
    role: str = "user",
    auth_provider: str = "password",
    allowed_environments: list[str] | None = None,
):
    """
    Move user from pending → approved.
    - For password users: requires hashed_password, sets must_change_pw=True.
    - For Google users: no password, sets must_change_pw=False.
    - allowed_environments: list of environments the user may access (e.g. ["prod","stage","dev"]).
      Defaults to ["prod"] when not specified.
    """

    if allowed_environments is None:
        allowed_environments = ["prod"]

    # Fetch pending user
    pending = dynamodb.get_item(
        TableName=PENDING_USERS_TABLE,
        Key={"user_email": {"S": email}}
    )

    if "Item" not in pending:
        raise Exception(f"User {email} not found in pending table")

    user = pending["Item"]

    # Base user item
    item = {
        "user_email": {"S": email},
        "status": {"S": "approved"},
        "role": {"S": role},
        "auth_provider": {"S": auth_provider},
        "full_name": user.get("full_name", {"S": ""}),
        "organization": user.get("organization", {"S": ""}),
        "job_title": user.get("job_title", {"S": ""}),
        "additional_info": user.get("additional_info", {"S": ""}),
        "allowed_environments": {"L": [{"S": env} for env in allowed_environments]},
    }

    if auth_provider == "password":
        if not hashed_password:
            raise ValueError("Password users must have a hashed_password")
        item["password_hash"] = {"S": hashed_password}
        item["must_change_pw"] = {"BOOL": True}
    else:
        # Google users: no password hash, no forced change
        item["must_change_pw"] = {"BOOL": False}

    # Write into approved table
    dynamodb.put_item(TableName=APPROVED_USERS_TABLE, Item=item)

    # Remove from pending table
    dynamodb.delete_item(
        TableName=PENDING_USERS_TABLE,
        Key={"user_email": {"S": email}}
    )

    logger.info(f"✅ Approved {email} as {role} via {auth_provider}")
    return item

def update_password(email: str, hashed_pw: str, must_change_pw: bool = None):
    """Update password, and optionally toggle must_change_pw."""
    update_expr = "SET password_hash = :pw"
    expr_values = {":pw": {"S": hashed_pw}}

    if must_change_pw is not None:
        update_expr += ", must_change_pw = :mcp"
        expr_values[":mcp"] = {"BOOL": must_change_pw}

    dynamodb.update_item(
        TableName=APPROVED_USERS_TABLE,
        Key={"user_email": {"S": email}},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
    )

def deny_user(email: str):
    """
    Mark a pending user as denied (soft delete) instead of moving tables.
    """
    email = email.strip().lower()

    # Check if user exists in pending table
    res = dynamodb.get_item(
        TableName=PENDING_USERS_TABLE,
        Key={"user_email": {"S": email}},
    )

    if "Item" not in res:
        raise Exception(f"User {email} not found in pending table")

    # Update the user's status to 'denied'
    dynamodb.update_item(
        TableName=PENDING_USERS_TABLE,
        Key={"user_email": {"S": email}},
        UpdateExpression="SET #status = :status",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":status": {"S": "denied"}},
    )

    logger.info(f"🚫 Denied user: {email}")
    return True

def get_admin_users():
    """
    Get all users with admin role from approved users table.
    Returns list of admin user items.
    """
    try:
        resp = dynamodb.scan(
            TableName=APPROVED_USERS_TABLE,
            FilterExpression="#role = :admin_role",
            ExpressionAttributeNames={"#role": "role"},
            ExpressionAttributeValues={":admin_role": {"S": "admin"}},
        )
        return resp.get("Items", [])
    except Exception as e:
        logger.error(f"Error scanning admin users: {e}")
        raise
