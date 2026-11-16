# bioinsight_ai/web_auth/main.py
import logging

# 🚫 Disable all uvicorn access logs permanently
logging.getLogger("uvicorn.access").disabled = True
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

from fastapi import FastAPI, Request
from log_helper.logger import get_logger

logger = get_logger()
app = FastAPI()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Logs requests and responses for all routes except internal health/auth checks.
    Suppresses noisy endpoints like /auth/verify and /health entirely.
    """
    excluded_paths = {"/auth/verify", "/health"}

    should_log = request.url.path not in excluded_paths

    if should_log:
        logger.info(f"➡️ Incoming request: {request.method} {request.url.path}")

    response = await call_next(request)

    if should_log:
        logger.info(f"⬅️ Response: {response.status_code} for {request.url.path}")

    return response


# ✅ Root-level health check for ALB / Nginx
@app.get("/health")
def root_health():
    return {"status": "ok"}


# ✅ Import and register routers
from .auth_routes import router as auth_router
from .admin_routes import router as admin_router

app.include_router(auth_router, prefix="/auth")
app.include_router(admin_router, prefix="/admin")
