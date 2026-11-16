# /web_auth/auth_routes.py
import os, random, string, time
import boto3
import httpx
from fastapi import APIRouter, HTTPException, Form, Depends, Response, Body, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode

from .utils.security import hash_password, verify_password, create_access_token, validate_password, VALID_ENVIRONMENTS
from .utils.dynamo import (
    get_user,
    save_pending_user,
    update_password,
    approve_user,
    get_pending_users,
)
from .utils.email_renderer import render_email
from .utils.email import send_temp_password, send_email, send_admin_notification
from log_helper.logger import get_logger
from config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    JWT_SECRET,
    JWT_ALGORITHM,
    APP_ENV,
)

from config import PENDING_USERS_TABLE, SES_SOURCE
dynamodb = boto3.client(
    "dynamodb",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)

logger = get_logger()
router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# === GOOGLE OAUTH CONFIG ===
GOOGLE_CLIENT_ID = os.getenv("OAUTH_GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("OAUTH_GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("OAUTH_GOOGLE_REDIRECT_URI")
APP_LOGIN_URL = os.getenv("APP_LOGIN_URL")
LOGO_URL = os.getenv("APP_LOGO_URL", "https://stage.bioinsight-ai.com/logo?theme=light&")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"

def generate_temp_password(length: int = 12) -> str:
    """Generate a secure random temporary password."""
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(random.choice(chars) for _ in range(length))

def get_current_admin(token: str = Depends(oauth2_scheme)):
    """Validate JWT and ensure admin role."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        role = payload.get("role")
        if role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/login")
def login(
    identifier: str = Form(...),
    password: str = Form(...),
    response: Response = None
):
    normalized_identifier = identifier.strip().lower()   # ✅ normalize
    logger.info(f"Login attempt for identifier={normalized_identifier}")

    user = get_user(normalized_identifier)   # ✅ always lowercase when fetching
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password.")

    # 🚫 Google block as before
    if user.get("auth_provider", {}).get("S") == "google":
        raise HTTPException(
            status_code=400,
            detail="This account uses Google sign-in. Please login with Google."
        )

    if not verify_password(password, user["password_hash"]["S"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")

    if user.get("must_change_pw", {}).get("BOOL", False):
        logger.info(f"User {normalized_identifier} must change password before login")
        return {
            "force_change_pw": True,
            "detail": "Password reset required before continuing"
        }

    logger.info(f"Login successful for {normalized_identifier}")
    full_name = user.get("full_name", {}).get("S", normalized_identifier)

    # ✅ Validate environment access
    allowed_envs = [item["S"] for item in user.get("allowed_environments", {}).get("L", [])]
    # Legacy users without the field get access to all environments
    # "local" is treated as "dev" for access control
    effective_env = "dev" if APP_ENV == "local" else APP_ENV
    if allowed_envs and effective_env not in allowed_envs:
        logger.warning(f"User {normalized_identifier} not allowed in environment '{APP_ENV}'")
        raise HTTPException(
            status_code=403,
            detail="Your account is not authorized to access this application environment."
        )

    token = create_access_token({
        "sub": normalized_identifier,   # ✅ always lowercase in token
        "role": user["role"]["S"],
        "full_name": full_name,
        "environment": APP_ENV,
    })

    if response:
        response.set_cookie(
            key="token",
            value=token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="Lax",
            max_age=7 * 24 * 60 * 60,
        )

    return {
        "access_token": token,
        "token_type": "bearer",
        "message": "Login successful",
        "full_name": full_name,
        "role": user["role"]["S"]
    }

@router.post("/signup")
def signup(
    full_name: str = Form(...),
    email: str = Form(...),
    organization: str = Form(...),
    job_title: str = Form(...),
    additional_info: str = Form(default=""),
    response: Response = None
):
    email = email.strip().lower()   # ✅ normalize
    logger.info(
        f"Signup request: full_name={full_name}, email={email}, org={organization}, job_title={job_title}"
    )

    existing = get_user(email)
    if existing:
        logger.warning(f"Signup blocked: user {email} already exists")

        query = urlencode({
            "error": f"An account with {email} already exists. Please log in instead."
        })
        # ✅ Return immediately so JSON below is NOT sent
        return RedirectResponse(url=f"/login?{query}", status_code=303)

    # Save as pending user
    save_pending_user(full_name, email, organization, job_title, additional_info)

    # ✅ Notify admins of new signup
    try:
        send_admin_notification(
            full_name=full_name,
            email=email,
            organization=organization,
            job_title=job_title,
            additional_info=additional_info,
            auth_provider="password",
            logo_url=LOGO_URL,
            admin_panel_url=f"{APP_LOGIN_URL}/admin"
        )
        logger.info(f"Admin notifications sent for new signup: {email}")
    except Exception as e:
        logger.error(f"Failed to send admin notification for {email}: {e}")
        # Don't fail the signup if admin notification fails

    subject = "Your BioInsight AI signup request has been received"
    plain_text = (
        f"Hello {full_name},\n\n"
        f"Thank you for signing up for BioInsight AI.\n"
        f"Your request is pending admin approval.\n\n"
        f"Submitted details:\n"
        f"- Email: {email}\n"
        f"- Organization: {organization}\n"
        f"- Job Title: {job_title}\n"
        f"- Additional Info: {additional_info or 'N/A'}\n\n"
        "We’ll notify you once approved.\n\nThank you,\nBioInsight AI Team"
    )
    html_body = render_email(
        "email/signup_request.html",
        subject=subject,
        full_name=full_name,
        email=email,
        organization=organization,
        job_title=job_title,
        additional_info=additional_info,
        logo_url=LOGO_URL,
        login_url=APP_LOGIN_URL,
    )

    try:
        send_email(email, subject, plain_text, html_body)
        logger.info(f"Signup confirmation email sent to {email}")
    except Exception:
        logger.error(f"Failed to send signup confirmation email to {email}")

    return {"message": "Signup request submitted. Await admin approval."}


@router.get("/admin/pending-users")
def list_pending_users(current_admin: dict = Depends(get_current_admin)):
    return {"users": get_pending_users()}

@router.post("/admin/approve")
def admin_approve(
    email: str = Form(...),
    role: str = Form(default="user"),
    allowed_environments: str = Form(default="prod"),
    current_admin: dict = Depends(get_current_admin),
    response: Response = None
):
    email = email.strip().lower()   # ✅ normalize

    # Parse comma-separated environments into a validated list
    env_list = [e.strip().lower() for e in allowed_environments.split(",") if e.strip()]
    env_list = [e for e in env_list if e in VALID_ENVIRONMENTS]
    if not env_list:
        env_list = ["prod"]

    logger.info(f"Admin approving user {email} with role={role}, environments={env_list}")

    pending = dynamodb.get_item(
        TableName=PENDING_USERS_TABLE,
        Key={"user_email": {"S": email}}
    )
    if "Item" not in pending:
        raise HTTPException(status_code=404, detail="User not found in pending table")

    user = pending["Item"]
    auth_provider = user.get("auth_provider", {}).get("S")
    if not auth_provider:
        logger.warning(f"User {email} missing auth_provider in pending table → defaulting to password")
        auth_provider = "password"

    try:
        logger.info(f"AUTHENTICATION PROVIDER CHECK - {auth_provider}")
        if auth_provider == "password":
            # 🔑 Password user → generate temp password
            temp_password = generate_temp_password()
            hashed_temp_password = hash_password(temp_password)
            approve_user(email, hashed_temp_password, role, auth_provider="password", allowed_environments=env_list)

            logger.info("USER APPROVED (PASSWORD) - SENDING EMAIL")

            subject = "Your BioInsight AI account has been approved"
            plain_text = (
                f"Hello,\n\nYour BioInsight AI account has been approved.\n\n"
                f"Temporary Password: {temp_password}\n\n"
                f"Login here: {APP_LOGIN_URL}\n\n"   # ✅ use env var
                "Please change your password upon first login.\n\nThank you,\nBioInsight AI Team"
            )
            html_body = render_email(
                "email/approval.html",
                subject=subject,
                temp_password=temp_password,
                role=role,
                login_url=APP_LOGIN_URL,
                logo_url=LOGO_URL,
            )

        elif auth_provider == "google":
            # 🔑 Google user → no password
            approve_user(email, None, role, auth_provider="google", allowed_environments=env_list)

            logger.info("USER APPROVED (GOOGLE) - SENDING EMAIL")

            subject = "Your BioInsight AI account has been approved"
            plain_text = (
                f"Hello,\n\nYour BioInsight AI account has been approved.\n\n"
                f"You may now log in using your Google account ({email}).\n\n"
                f"Login here: {APP_LOGIN_URL}\n\n"   # ✅ use env var
                "Thank you,\nBioInsight AI Team"
            )
            html_body = render_email(
                "email/google_approval.html",
                subject=subject,
                email=email,
                login_url=APP_LOGIN_URL,   # ✅ pass env var into template
                role=role,
                logo_url=LOGO_URL,
            )

        else:
            logger.error(f"Unknown auth_provider={auth_provider} for {email}")
            raise HTTPException(status_code=400, detail="Unsupported auth provider")

        try:
            send_email(email, subject, plain_text, html_body)
            logger.info(f"Signup confirmation email sent to {email}")
        except Exception:
            logger.error(f"Failed to send signup confirmation email to {email}")

    except Exception as e:
        logger.error(f"Approval failed for {email}: {e}")
        raise HTTPException(status_code=500, detail="User approval failed")

    return {"message": f"User {email} approved and email sent."}

# === GOOGLE AUTH ===
@router.get("/google/login")
def google_login():
    """Redirect to Google OAuth consent screen"""
    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
    )

    # ✅ Log the full redirect URL for debugging
    logger.info(f"🔗 Google OAuth redirect URL: {google_auth_url}")

    return RedirectResponse(google_auth_url)

@router.get("/google/callback")
async def google_callback(request: Request, response: Response, code: str):
    logger.info(f"➡️ Google callback hit at {GOOGLE_REDIRECT_URI} with code={code}")

    token_url = "https://oauth2.googleapis.com/token"

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(token_url, data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        })
        token_data = token_resp.json()

    id_info = id_token.verify_oauth2_token(
        token_data["id_token"], grequests.Request(), GOOGLE_CLIENT_ID
    )

    email = id_info.get("email", "").strip().lower()   # ✅ normalize once here
    full_name = id_info.get("name", "")

    user = get_user(email)

    if user:
        if user.get("auth_provider", {}).get("S") == "password":
            query = urlencode({
                "error": "This account uses password login. Please sign in with email and password."
            })
            return RedirectResponse(url=f"/login?{query}")

        role = user["role"]["S"]

        # ✅ Validate environment access for Google users
        allowed_envs = [item["S"] for item in user.get("allowed_environments", {}).get("L", [])]
        # "local" is treated as "dev" for access control
        effective_env = "dev" if APP_ENV == "local" else APP_ENV
        if allowed_envs and effective_env not in allowed_envs:
            logger.warning(f"Google user {email} not allowed in environment '{APP_ENV}'")
            query = urlencode({
                "error": "Your account is not authorized to access this application environment."
            })
            return RedirectResponse(url=f"/login?{query}")

    else:
        save_pending_user(full_name, email, "N/A", "N/A", "Google signup", auth_provider="google")
        
        # ✅ Notify admins of new Google signup
        try:
            send_admin_notification(
                full_name=full_name,
                email=email,
                organization="N/A",
                job_title="N/A",
                additional_info="Google signup",
                auth_provider="google",
                logo_url=LOGO_URL,
                admin_panel_url=f"{APP_LOGIN_URL}/admin"
            )
            logger.info(f"Admin notifications sent for new Google signup: {email}")
        except Exception as e:
            logger.error(f"Failed to send admin notification for Google user {email}: {e}")
        
        query = urlencode({"error": f"Your Google account ({email}) is pending admin approval."})
        return RedirectResponse(url=f"/login?{query}")

    # Only issue JWT if already approved
    payload = {
        "sub": email,   # ✅ already normalized above
        "full_name": full_name,
        "role": role,
        "environment": APP_ENV,
        "exp": int(time.time()) + 86400
    }
    jwt_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    response = RedirectResponse(url="/chat/")
    response.set_cookie(
        key="token", 
        value=jwt_token, 
        httponly=True, 
        secure=COOKIE_SECURE, 
        samesite="Lax", 
        max_age=7 * 24 * 60 * 60,
    )
    return response

@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("token", path="/", secure=COOKIE_SECURE)
    response.delete_cookie("access_token", path="/", secure=COOKIE_SECURE)
    return {"message": "Logged out successfully"}


@router.get("/verify")
def verify(request: Request):
    cookie_header = request.headers.get("cookie")
    token = None
    if cookie_header:
        for part in cookie_header.split(";"):
            if part.strip().startswith("token="):
                token = part.split("=", 1)[1].strip()
                break

    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        exp = payload.get("exp")
        if exp and int(exp) < int(time.time()):
            raise HTTPException(status_code=401, detail="Token expired")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    #Standardized response (matches /admin/verify)
    return {
        "status": "ok",
        "sub": payload.get("sub"),
        "full_name": payload.get("full_name"),
        "role": payload.get("role"),
        "exp": payload.get("exp"),   # include exp here
    }

@router.post("/change-password")
def change_password(
    email: str = Form(...),
    old_password: str = Form(...),
    new_password: str = Form(...),
    response: Response = None
):
    email = email.strip().lower()   # ✅ normalize
    validate_password(new_password, email)

    logger.info(f"Change-password attempt for {email} (first login)")

    user = get_user(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 🚫 Block Google accounts
    if user.get("auth_provider", {}).get("S") == "google":
        raise HTTPException(
            status_code=400,
            detail="Google accounts cannot change password. Please login with Google."
        )

    if not verify_password(old_password, user["password_hash"]["S"]):
        logger.warning(f"Change-password failed: incorrect old password for {email}")
        raise HTTPException(status_code=401, detail="Old password is incorrect")

    if verify_password(new_password, user["password_hash"]["S"]):
        raise HTTPException(
            status_code=400,
            detail="New password cannot be the same as the old password",
        )

    new_hashed = hash_password(new_password)
    update_password(email, new_hashed, must_change_pw=False)

    logger.info(f"Password successfully changed for {email}, must_change_pw cleared")

    subject = "Your BioInsight AI password has been changed"
    plain_text = (
        f"Hello {email},\n\n"
        f"Your password for BioInsight AI has been successfully changed.\n\n"
        f"If this was not you, please contact support immediately.\n\n"
        f"Login here: {APP_LOGIN_URL}\n\n"   # ✅ use env-based URL
        "Thank you,\nBioInsight AI Team"
    )
    html_body = render_email(
        "email/change_password.html",
        subject=subject,
        email=email,
        logo_url=LOGO_URL,
        login_url=APP_LOGIN_URL,
    )

    try:
        send_email(email, subject, plain_text, html_body)
        logger.info(f"Password reset confirmation email sent to {email}")
    except Exception:
        logger.error(f"Failed to send password reset confirmation email to {email}")

    return {"message": "Password changed successfully. Please login again."}

@router.post("/forgot-password")
def forgot_password(email: str = Form(...)):
    email = email.strip().lower()   # ✅ normalize
    logger.info(f"Forgot-password request for {email}")

    user = get_user(email)
    if not user:
        logger.warning(f"Forgot-password: no such user {email}")
        # ✅ Don’t reveal existence
        return {"message": "If your account is password-based, a reset email has been sent."}

    if user.get("auth_provider", {}).get("S") == "google":
        logger.info(f"Forgot-password: {email} is a Google account → skipping")
        return {"message": "If your account is password-based, a reset email has been sent."}

    # 🔑 Generate temp password
    temp_password = generate_temp_password()
    hashed_temp_password = hash_password(temp_password)

    # Update Dynamo: set must_change_pw=True
    update_password(email, hashed_temp_password, must_change_pw=True)
    logger.info(f"Temporary password set for {email}, must_change_pw=True")

    # Send email
    subject = "Your BioInsight AI temporary password"
    plain_text = (
        f"Hello {email},\n\n"
        f"You requested a password reset.\n\n"
        f"Temporary Password: {temp_password}\n\n"
        f"Login here: {APP_LOGIN_URL}\n\n"
        f"⚠️ Please change your password immediately after login.\n\n"
        "Thank you,\nBioInsight AI Team"
    )
    html_body = render_email(
        "email/forgot_password.html",
        subject=subject,
        temp_password=temp_password,
        email=email,
        login_url=APP_LOGIN_URL,
        logo_url=LOGO_URL,
    )

    try:
        send_email(email, subject, plain_text, html_body)
        logger.info(f"Forgot-password email sent to {email}")
    except Exception:
        logger.error(f"Failed to send forgot-password email to {email}")

    return {"message": "If your account is password-based, a reset email has been sent."}
