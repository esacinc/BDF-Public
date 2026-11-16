# web_auth/utils/dependencies.py
import time
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

from .security import decode_access_token
from config import JWT_SECRET, JWT_ALGORITHM
from log_helper.logger import get_logger

logger = get_logger()

# === Bearer-token flow (used for API clients, login endpoints, etc.) ===
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload

def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# === Cookie-based flow (used for frontend /admin panel) ===
def get_current_user_from_cookies(request: Request):
    logger.info("🔥 DEBUG (admin): Entered get_current_user_from_cookies")

    cookie_header = request.headers.get("cookie")
    logger.info(f"🔥 DEBUG (admin): Raw cookie header: {cookie_header}")

    token = None
    if cookie_header:
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith("token=") or part.startswith("access_token="):
                token = part.split("=", 1)[1].strip()
                logger.info(f"🔥 DEBUG (admin): Using cookie part: {part}")
                break

    if not token:
        logger.info("❌ DEBUG (admin): No token found in cookies")
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        logger.info(f"🔥 DEBUG (admin): Decoded JWT payload: {payload}")

        exp = payload.get("exp")
        if exp and int(exp) < int(time.time()):
            logger.info("❌ DEBUG (admin): Token expired")
            raise HTTPException(status_code=401, detail="Token expired")
    except JWTError as e:
        logger.info(f"❌ DEBUG (admin): Invalid token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

    return payload


def require_admin_cookie(user=Depends(get_current_user_from_cookies)):
    logger.info(f"🔥 DEBUG (admin): Inside require_admin_cookie, user: {user}")

    if user.get("role") != "admin":
        logger.info(f"❌ DEBUG (admin): User role is not admin: {user.get('role')}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    logger.info("✅ DEBUG (admin): User is admin")
    return user
