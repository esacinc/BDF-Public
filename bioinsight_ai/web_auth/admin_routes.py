# /web_auth/admin_routes.py
from fastapi import APIRouter, HTTPException, Form, Depends
from .utils.dynamo import get_pending_users, approve_user
from .utils.security import hash_password, VALID_ENVIRONMENTS
from .utils.email import send_email
from .utils.dependencies import require_admin_cookie
from .utils.email_renderer import render_email
from .utils.dynamo import deny_user
import secrets
import os

router = APIRouter()

# ✅ Use env var for login URL (no more hardcoded stage/prod URLs)
APP_LOGIN_URL = os.getenv("APP_LOGIN_URL", "https://stage.bioinsight-ai.com/login")
LOGO_URL = os.getenv("APP_LOGO_URL", "https://stage.bioinsight-ai.com/logo?theme=light&")

@router.get("/verify")
def admin_verify(user=Depends(require_admin_cookie)):
    """
    Standardized response shape, aligned with /auth/verify
    """
    return {
        "status": "ok",
        "sub": user.get("sub"),
        "full_name": user.get("full_name"),
        "role": user.get("role"),
        "exp": user.get("exp"),
    }

@router.get("/pending-users")
def list_pending_users(user=Depends(require_admin_cookie)):
    try:
        users = get_pending_users()
        return {"users": users}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching pending users: {str(e)}"
        )

@router.post("/approve")
def approve(
    email: str = Form(...),
    role: str = Form(default="user"),
    allowed_environments: str = Form(default="prod"),
    user=Depends(require_admin_cookie),
):
    email = email.strip().lower()  # ✅ normalize

    # Parse comma-separated environments into a validated list
    env_list = [e.strip().lower() for e in allowed_environments.split(",") if e.strip()]
    env_list = [e for e in env_list if e in VALID_ENVIRONMENTS]
    if not env_list:
        env_list = ["prod"]

    try:
        # Fetch pending user to check provider
        pending_users = get_pending_users()
        pending = next((u for u in pending_users if u["user_email"]["S"] == email), None)
        if not pending:
            raise HTTPException(status_code=404, detail="User not found in pending table")

        auth_provider = pending.get("auth_provider", {}).get("S", "password")

        if auth_provider == "password":
            # password-based approval → temp password + must change
            temp_password = secrets.token_urlsafe(10)
            hashed = hash_password(temp_password)
            approve_user(email, hashed, role=role, auth_provider="password", allowed_environments=env_list)

            env_label = ", ".join(env_list)
            subject = "Your BioInsight AI account has been approved"
            plain_text = (
                f"Hello,\n\nYour BioInsight AI account has been approved.\n\n"
                f"Temporary Password: {temp_password}\n\n"
                f"Login here: {APP_LOGIN_URL}\n\n"
                "Please change your password upon first login.\n\nThank you,\nBioInsight AI Team"
            )
            html_body = render_email(
                "email/approval.html",
                subject=subject,
                temp_password=temp_password,
                login_url=APP_LOGIN_URL,
                role=role,
                logo_url=LOGO_URL,
            )
            send_email(email, subject, plain_text, html_body)
            return {"message": f"User {email} approved with password and notified (environments: {env_label})"}

        elif auth_provider == "google":
            # Google-based approval → no password
            approve_user(email, None, role=role, auth_provider="google", allowed_environments=env_list)

            env_label = ", ".join(env_list)
            subject = "Your BioInsight AI account has been approved"
            plain_text = (
                f"Hello,\n\nYour BioInsight AI account has been approved.\n\n"
                f"You may now log in using your Google account ({email}).\n\n"
                f"Login here: {APP_LOGIN_URL}\n\n"
                "Thank you,\nBioInsight AI Team"
            )
            html_body = render_email(
                "email/google_approval.html",
                subject=subject,
                email=email,
                login_url=APP_LOGIN_URL,
                role=role,
                logo_url=LOGO_URL,
            )
            send_email(email, subject, plain_text, html_body)
            return {"message": f"Google user {email} approved and notified (environments: {env_label})"}

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported auth_provider: {auth_provider}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error approving user: {str(e)}")


@router.post("/deny")
def deny(
    email: str = Form(...),
    user=Depends(require_admin_cookie),
):
    try:
        deny_user(email)
        return {"message": f"User {email} denied successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error denying user: {str(e)}")
