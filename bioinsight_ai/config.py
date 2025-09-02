import os
from dotenv import load_dotenv
load_dotenv()

AWS_ACCESS_KEY = os.environ["AWS_ACCESS_KEY"]
AWS_REGION = os.environ["AWS_REGION"]
AWS_SECRET_KEY = os.environ["AWS_SECRET_KEY"]
CONTEXT_KB_ID = os.environ["CONTEXT_KB_ID"]
CONTEXT_SOURCE_ID = os.environ["CONTEXT_SOURCE_ID"]
DATA_LAYER_TABLE = os.environ["DATA_LAYER_TABLE"]
DEFAULT_MODEL = os.environ["DEFAULT_MODEL"]
MWB_KB_ID = os.environ["MWB_KB_ID"]
MWB_SOURCE_ID = os.environ["MWB_SOURCE_ID"]
PUBLICATIONS_KB_ID = os.environ["PUBLICATIONS_KB_ID"]
CHAINLIT_STORAGE_BUCKET = os.environ["CHAINLIT_STORAGE_BUCKET"]
FAST_MODEL = os.environ["FAST_MODEL"]
GDC_BASE_API = os.environ["GDC_BASE_API"]
