import os
from dotenv import load_dotenv
load_dotenv()

# Canonical AWS environment variable names expected by AWS SDKs
# Prefer AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY. For backwards compatibility
# support legacy names AWS_ACCESS_KEY and AWS_SECRET_KEY by falling back to them
# if the canonical names are not present.
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_ACCESS_KEY")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("AWS_SECRET_KEY")
AWS_REGION = os.environ.get("AWS_REGION")

DATA_LAYER_TABLE = os.environ["DATA_LAYER_TABLE"]
FEEDBACK_TABLE = os.environ["FEEDBACK_TABLE"]
DEFAULT_MODEL = os.environ["DEFAULT_MODEL"]
MWB_KB_ID = os.environ["MWB_KB_ID"]
MWB_SOURCE_ID = os.environ["MWB_SOURCE_ID"]
PUBLICATIONS_KB_ID = os.environ["PUBLICATIONS_KB_ID"]
PUBLICATIONS_DOCS_SOURCE_ID = os.environ["PUBLICATIONS_DOCS_SOURCE_ID"]
PUBLICATIONS_FAQ_S3_SOURCE_ID = os.environ["PUBLICATIONS_FAQ_S3_SOURCE_ID"]
PUBLICATIONS_FAQ_WEB_SOURCE_ID = os.environ["PUBLICATIONS_FAQ_WEB_SOURCE_ID"]
PUBLICATIONS_PAPERS_SOURCE_ID = os.environ["PUBLICATIONS_PAPERS_SOURCE_ID"]
CHAINLIT_STORAGE_BUCKET = os.environ["CHAINLIT_STORAGE_BUCKET"]
GDC_BASE_API = os.environ["GDC_BASE_API"]
APPROVED_USERS_TABLE = os.environ["APPROVED_USERS_TABLE"]
PENDING_USERS_TABLE = os.environ["PENDING_USERS_TABLE"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = os.environ["JWT_ALGORITHM"]
SES_SOURCE = "no-reply@bioinsight-ai.com"

# Deployment environment: "dev", "stage", or "prod"
APP_ENV = os.environ.get("APP_ENV", "prod")

# S3 CORS Configuration
# Comma-separated list of allowed origins for S3 presigned URL access
# Local: "http://localhost:3000"
# AWS Dev: "https://dev-api.bioinsight.com"
# Prod: "https://bioinsight.com"
# For development, can use "*" to allow all origins (NOT recommended for production)
ALLOWED_CORS_ORIGINS = os.environ.get("ALLOWED_CORS_ORIGINS", "*").split(",")
ALLOWED_CORS_ORIGINS = [origin.strip() for origin in ALLOWED_CORS_ORIGINS if origin.strip()]
