import boto3
import chainlit as cl
import chainlit.types as cl_types
from config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    DATA_LAYER_TABLE,
    FEEDBACK_TABLE,
    CHAINLIT_STORAGE_BUCKET,
    JWT_SECRET,
    JWT_ALGORITHM,
    ALLOWED_CORS_ORIGINS,
    APP_ENV,
)
from bioinsight_workflow import bioinsight_session
from jose import jwt, JWTError
from plotly.graph_objs import Figure
import plotly.graph_objects as go
import plotly.io as pio
import base64
import requests
import uuid
import gzip
from workflows.errors import ContextStateError
from storage.presigned_s3_client import PreSignedS3Client
from storage.s3_cors_config import configure_s3_cors, verify_s3_cors
from data_sources.metabolomics_workbench import MolView
from utils.chainlit_loader import update_loader_message
from workflow_config.events import (
    ResponseEvent, 
    ConcludeEvent
    )
from workflow_config.steps.orchestration.plan import Plan, Action
from llama_index.core.agent.workflow.workflow_events import AgentStream
from llama_index.core.workflow import Context, JsonSerializer
from log_helper.logger import get_logger
from fastapi import Request

from chainlit import User, Message
from log_helper.logger import current_thread_id, current_user_email
from integrations.chainlit.on_chat_start import greeting, suggested_query_callback
from integrations.chainlit.on_message import link_plan_to_message

logger = get_logger()

# AWS Clients
logger.info("Initializing AWS DynamoDB and S3 clients.")
client = boto3.client(
    "dynamodb",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)

storage_provider = PreSignedS3Client(
    bucket=CHAINLIT_STORAGE_BUCKET,
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    presigned_url_expiration=604800,  # 7 days
)

# ✅ Modern DataLayer setup using DataLayerManager
from integrations.chainlit.on_feedback.data_layer_manager import DataLayerManager

# Initialize data layer manager
data_layer_manager = DataLayerManager(
    conversation_table=DATA_LAYER_TABLE,
    feedback_table=FEEDBACK_TABLE,
    client=client,
    storage_provider=storage_provider
)

# Configure Chainlit data layers
data_layer_manager.configure_chainlit_layers()

# Set up feedback data layer
data_layer_manager.setup_feedback_layer()

# Get individual data layers for use in the application
dynamodb_layer = data_layer_manager.get_conversation_layer()
feedback_layer = data_layer_manager.get_feedback_layer()

# Validate data layer configuration
data_layer_manager.validate_configuration()

# Validate environment configuration
def validate_environment_configuration():
    """
    Validate all required environment variables for feedback collection.
    """
    missing_vars = []
    invalid_vars = []
    
    # Check required environment variables
    if not FEEDBACK_TABLE:
        missing_vars.append("FEEDBACK_TABLE")
    
    if not DATA_LAYER_TABLE:
        missing_vars.append("DATA_LAYER_TABLE")
    
    if not AWS_ACCESS_KEY_ID:
        missing_vars.append("AWS_ACCESS_KEY_ID")
    
    if not AWS_SECRET_ACCESS_KEY:
        missing_vars.append("AWS_SECRET_ACCESS_KEY")
    
    if not AWS_REGION:
        missing_vars.append("AWS_REGION")
    
    if not CHAINLIT_STORAGE_BUCKET:
        missing_vars.append("CHAINLIT_STORAGE_BUCKET")
    
    # Report validation results
    if missing_vars:
        error_msg = f"❌ Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    if invalid_vars:
        error_msg = f"❌ Invalid environment variable values: {'; '.join(invalid_vars)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info("✅ Environment configuration validation passed")

# Validate environment configuration at startup
validate_environment_configuration()

# Configure S3 CORS to allow browser access to presigned URLs
logger.info("Configuring S3 CORS for presigned URL access...")
logger.info(f"  Allowed origins: {ALLOWED_CORS_ORIGINS}")
logger.info(f"  Environment: {APP_ENV}")

cors_success = configure_s3_cors(
    bucket=CHAINLIT_STORAGE_BUCKET,
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    allowed_origins=ALLOWED_CORS_ORIGINS,
)

if cors_success:
    # Verify CORS configuration
    verify_s3_cors(
        bucket=CHAINLIT_STORAGE_BUCKET,
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )
else:
    logger.warning(
        f"Failed to configure S3 CORS on bucket '{CHAINLIT_STORAGE_BUCKET}'. "
        "CORS headers may need to be configured manually on the S3 bucket. "
        "Without proper CORS configuration, browser clients may be unable to access presigned URLs."
    )

logger.info("✅ Data layers ready")
logger.info(f"   Conversation: {DATA_LAYER_TABLE}")
logger.info(f"   Feedback: {FEEDBACK_TABLE}")
# Get the underlying FastAPI app from Chainlit
from chainlit.server import app as fastapi_app

from typing import Optional, Dict
from chainlit import User

@cl.header_auth_callback
def auth_from_cookie(headers: Dict) -> Optional[User]:
    """
    Authenticate user from JWT stored in 'token' cookie only.
    Ignore any 'access_token' cookie left over by frontend.
    """
    cookie_header = headers.get("cookie")
    if not cookie_header:
        logger.warning("❌ No cookie header found")
        return None

    #logger.debug(f"Raw cookie header: {cookie_header}")

    # Parse cookies into dict
    cookies = dict(h.split("=", 1) for h in cookie_header.split("; ") if "=" in h)

    # 🚫 Ignore access_token explicitly
    if "access_token" in cookies:
        logger.debug("⚠️ Ignoring 'access_token' cookie (not used for Chainlit auth)")

    token = cookies.get("token")
    if not token:
        logger.warning("❌ No 'token' cookie found")
        return None

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            logger.error("JWT missing sub")
            return None

        full_name = payload.get("full_name", "User")
        role = payload.get("role", "user")

        logger.info(f"✅ Authenticated {user_id} via cookie")
        return User(
            identifier=user_id,
            metadata={
                "full_name": full_name,
                "role": role,
                "jwt_payload": payload,
            },
        )

    except JWTError as e:
        logger.error(f"JWT decode failed: {e}")
        return None

def is_base64_png(data: str) -> bool:
    """
    Basic heuristic to check if a string is a base64-encoded PNG.
    """
    # return isinstance(data, str) and len(data) > 100 and re.match(r'^[A-Za-z0-9+/]+={0,2}$', data)
    if not isinstance(data, str) or len(data) < 100:
        return False
    try:
        decoded = base64.b64decode(data)
        logger.debug(decoded[:10])
        return decoded.startswith(b'\x89PNG\r\n\x1a\n')
    except Exception as e:
        logger.debug(f"Not valid base64: {e}")
        return False


async def decode_plotly_figure(encoded_str):
    decoded = base64.b64decode(encoded_str)
    decompressed = gzip.decompress(decoded).decode('utf-8')
    fig = pio.from_json(decompressed)
    return fig

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Breast Cancer Studies in Metabolomics Workbench",
            message="List all breast cancer studies in Metabolomics Workbench that focus on chemotherapy response",
        ),

        cl.Starter(
            label="GBM Datasets in PDC",
            message="Can you provide information on any available GBM datasets in the PDC?",
        ),
        cl.Starter(
            label="Generate a Plot for Gene Expression in a Proteomic Study",
            message="Generate a violin plot for CDKN2A, MDM2, and TP53 expression in Study PDC000173",
        ),
        cl.Starter(
            label="Pan-Cancer Data Analysis Challenges",
            message="What are the analytical challenges in performing a pan-cancer analysis?",
        ),
        cl.Starter(
            label="Show MRI Sequences Count in Imaging Data",
            message="How many MRI sequences are present in Imaging Data Commons?",
        )
    ]

@cl.on_chat_start
async def start():
    logger.info("Chat session started.")
    # Send a startup loader immediately so the UI shows progress while we initialize
    loader_state = {"sent": False, "last_message": None}
    startup_loader_id = str(uuid.uuid4())
    startup_loader = cl.CustomElement(name="loader", id=startup_loader_id, props={"message": "Starting BioInsight..."})
    startup_loader_msg = cl.Message(content="", elements=[startup_loader])
    try:
        await startup_loader_msg.send()
        loader_state['sent'] = True
        loader_state['last_message'] = startup_loader_msg.content
        cl.user_session.set("loader_state", loader_state | {'loader_msg': startup_loader_msg})
    except Exception:
        logger.exception("Failed to send startup loader message")
    try:
        # ✅ Retrieve authenticated user
        user: User = cl.user_session.get("user")
        if not user:
            await Message(content="❌ Authentication failed. Please login again.").send()
            return

        # ✅ Extract user + thread info
        user_id = user.identifier
        full_name = user.metadata.get("full_name", "User")
        role = user.metadata.get("role", "user")
        thread_id = cl.context.session.thread_id

        # ✅ Store in Chainlit session
        cl.user_session.set("user_id", user_id)
        cl.user_session.set("thread_id", thread_id)
        cl.user_session.set("role", role)
        cl.user_session.set("full_name", full_name)

        # ✅ Store globally for logger context propagation
        current_thread_id.set(thread_id)
        current_user_email.set(user_id)

        logger.info(f"✅ User identity set: {user_id}, role={role}, thread={thread_id}")

        # ✅ Initialize workflow
        session_id = cl.user_session.get("id")
        logger.info(f"Starting session: {session_id}")

        wf = await bioinsight_session(session_id, presigned_s3_client=storage_provider)
        ctx = Context(wf)

        cl.user_session.set("wf", wf)
        cl.user_session.set("ctx", ctx)

        logger.info("✅ Workflow session initialized successfully.")

        # If a cached opening salutation exists, show it to the user immediately for faster load.
        try:
            opening_message = greeting.deserialize_chainlit_message()
        except Exception:
            logger.exception("Failed to read/send cached opening salutation falling back to Chainlit Starters.")

        if opening_message:
            await opening_message.send()
        else:
            logger.warning("⚠️  No opening_message found.")

    finally:
        # Always remove the startup loader regardless of success/failure
        try:
            stored = cl.user_session.get("loader_state") or (loader_state | {'loader_msg': startup_loader_msg})
            await update_loader_message(stored.get('loader_msg', startup_loader_msg), stored, startup_loader_id, remove=True)
            cl.user_session.set("loader_state", None)
        except Exception:
            logger.exception("Failed to remove startup loader")


#########Helper functions for event handling and formatting#########

# Format helper
def format_column_list(columns):
    if not columns:
        return "selected columns"
    if len(columns) == 1:
        return columns[0]
    elif len(columns) == 2:
        return f"{columns[0]} and {columns[1]}"
    else:
        return ", ".join(columns[:-1]) + f", and {columns[-1]}"

# Helper to safely fetch a URL JSON -> Figure
async def _fig_from_url(url: str):
    r = requests.get(url)
    r.raise_for_status()
    # Important: do NOT json.loads
    fig = pio.from_json(r.text)
    return fig
###################################################################

@cl.on_message
async def on_message(message: cl.Message):
    # session concurrency guard — prevent overlapping handler runs in same session
    running = cl.user_session.get("running", False)
    if running:
        logger.info("Rejected concurrent message while previous handler running.")
        await cl.Message(content="Another request is still being processed. Please wait a moment.").send()
        return
    cl.user_session.set("running", True)

    if message.content:
        user = cl.user_session.get("user")
        thread_id = cl.user_session.get("thread_id")
        if user and thread_id:
            current_thread_id.set(thread_id)
            current_user_email.set(user.identifier)

        # Clear any previous plan to avoid stale associations with new messages
        cl.user_session.set('current_plan', None)

        logger.info("Received message: %s", message.content)
        cl.user_session.set("user_query", message.content)
        wf = cl.user_session.get("wf")
        ctx = cl.user_session.get("ctx")

        if wf is None:
            logger.warning("Workflow not found in session.")
            await cl.Message(content="Workflow not found. Please refresh the session.").send()
            return

        try:
            logger.info("Running workflow...")
            
            # Remove any existing TaskList from a previous run (stored in session)
            prev_tasklist = cl.user_session.get('tasklist')
            if prev_tasklist:
                 try:
                    await prev_tasklist.remove()
                 except Exception:
                    logger.exception("Failed to remove previous TaskList on new message start.")
                 finally:
                    cl.user_session.set('tasklist', None)
                
            # Initialize loader state
            loader_state = cl.user_session.get("loader_state") or {"sent": False, "last_message": None}
            loader_id = str(uuid.uuid4())
            loader = cl.CustomElement(
                    name="loader",
                    id=loader_id,
                    props={
                'message':"Thinking about your query..."
            })
            
            # send initial loader
            loader_msg = cl.Message(content="", elements=[loader])
            await loader_msg.send()
            loader_state['sent'] = True
            loader_state['last_message'] = loader_msg.content
            cl.user_session.set("loader_state", loader_state | {'loader_msg': loader_msg})
            # send query to workflow
            handler = wf.run(query=message.content, ctx=ctx)
            cl.user_session.set("handler", handler) # store handler

            # do not duplicate loading bar events
            event_started = dict.fromkeys([
                    "execute_task",
                    "synthesizing_results",
                    "concluding"
                    ], False)
            seen_agent_tools = set()
            
            # stream handler events
            async for event in handler.stream_events(): 
                if isinstance(event, Action) and not event_started["execute_task"]:
                    event_started["execute_task"] = True
                    cl.user_session.set("loader_state", 
                                            await update_loader_message(loader_msg, loader_state, loader_id, "Executing tasks...")
                                            )
                elif isinstance(event, Plan):
                    # Convert plan to a TaskList, send it and store on the user session
                    tasklist = event.to_tasklist()
                    try:
                        await tasklist.send()
                    except Exception:
                        logger.exception("Failed to send TaskList for Plan event.")
                    cl.user_session.set('tasklist', tasklist)
                    
                    # ✅ Store the Plan object for feedback collection
                    try:
                        # Store plan in session for later linking to message
                        cl.user_session.set('current_plan', event)
                        logger.info(f"Stored plan in session with {len(event.actions)} actions")
                        
                        # Note: Plan will be linked to message ID after message is sent
                        # See link_plan_to_message() calls after msg.send()
                    except Exception as e:
                        logger.warning(f"Failed to store plan in session: {e}")
                        # Don't fail the workflow if plan storage fails
                elif isinstance(event, AgentStream):
                     for tool_call in event.tool_calls:
                        tool_id = tool_call.tool_id
                        tool_name = tool_call.tool_name
                        kwargs = tool_call.tool_kwargs

                        # Skip if we've already shown a message for this tool call
                        if tool_id in seen_agent_tools:
                            continue

                        # Determine message only when required args are present
                        status_message = None
                        if tool_name == "match_schema":
                            status_message = "Generating schema matches..."
                        elif tool_name == "rank_schema_matches" and kwargs.get("columns"):
                            status_message = f"Generating matches for {format_column_list(kwargs['columns'])}..."
                        elif tool_name == "process_schema_match_feedback" and kwargs.get("source_columns"):
                            status_message = f"Updating mapping for {format_column_list(kwargs['source_columns'])}..."
                        elif tool_name == "match_values" and kwargs.get("target_dataset_path"):
                            status_message = f"Generating value mappings for {kwargs['target_dataset_path']}..."
                        elif tool_name == "materialize_mapping":
                            status_message = "Harmonizing user dataset..."
                        elif tool_name == "return_data_to_user":
                            status_message = "Preparing dataset for download..."

                        # Show loader only if message is ready
                        if status_message:
                            cl.user_session.set("loader_state", 
                                                await update_loader_message(loader_msg, loader_state, loader_id, status_message)
                            )
                            seen_agent_tools.add(tool_id)
                    
                elif isinstance(event, ResponseEvent) and not event_started["synthesizing_results"]:
                    event_started["synthesizing_results"] = True
                    cl.user_session.set("loader_state", 
                                        await update_loader_message(loader_msg, loader_state, loader_id, "Synthesizing results...")
                    )
                elif isinstance(event, ConcludeEvent) and not event_started["concluding"]:
                    event_started["concluding"] = True
                    cl.user_session.set("loader_state", 
                                        await update_loader_message(loader_msg, loader_state, loader_id, "Finalizing response...")
                    )
            if message:
                logger.info("Chainlit_app.py - on_message: Before result = await handler query: %s", message.content)
            else:
                logger.info("Chainlit_app.py - on_message: Before result = await handler message is Missing!!!")
            result = await handler
            cl.user_session.set("loader_state",
                                        await update_loader_message(loader_msg, loader_state, loader_id, remove=True)
            )
            logger.info("Workflow completed.")
            logger.info(result)

            # Refresh serialized_ctx after each successful turn so on_chat_end
            # always has a complete snapshot to persist, even if it later hits
            # an error path. Chainlit's disconnect handler will write whatever
            # is in user_session into thread metadata.
            try:
                await wf.flush_memory_to_context(ctx)
                cl.user_session.set("serialized_ctx", ctx.to_dict(serializer=JsonSerializer()))
            except Exception as e:
                logger.warning(f"Failed to refresh serialized_ctx after turn: {e}")

            elements = []
            graph_meta = None

            # Prefer explicit graph / graphs / graph_data keys
            try:
                if isinstance(result, dict) and ('graph' in result or 'graphs' in result):
                    # graph_payload = result.get('graph') or (result.get('graphs') and result.get('graphs')[0])
                    graph_payload = result.get('graph') or result.get('graphs')
                    logger.info(f"on_message: trying to render graph in UI - graph_payload type: {type(graph_payload)}")
                    # ✅ NEW: handle list of figures
                    if isinstance(graph_payload, list):
                        logger.info("on_message: case where graph_payload is a list")
                        graph_meta_list = []
                        for item in graph_payload:
                            if isinstance(item, dict) and item.get("type") == "plotly_url":
                                fig = await _fig_from_url(item["url"])
                                elements.append(
                                    cl.Plotly(
                                        name="chart",
                                        figure=fig,
                                        display="inline", 
                                        size="large"
                                    )
                                )
                                graph_meta_curr = {
                                    "graph": "s3_figure_list",
                                    "s3_object_key": item.get("objectKey"),
                                    "s3_url": item.get("url")
                                }
                                graph_meta_list.append(graph_meta_curr)
                                logger.info(f"Added Plotly figure from URL in list with metadata: {graph_meta_curr}")
                        graph_meta = graph_meta_list

                    # Handle single S3 graph object
                    elif isinstance(graph_payload, dict) and "url" in graph_payload and "objectKey" in graph_payload:
                        logger.info("on_message: case where graph_payload is a dict with S3 metadata")
                        fig = await _fig_from_url(graph_payload["url"])
                        elements.append(
                            cl.Plotly(
                                name="chart",
                                figure=fig,
                                display="inline",
                                size="large"
                            )
                        )
                        graph_meta = {
                            "graph_data": graph_payload,
                            "s3_object_key": graph_payload.get("objectKey"),
                            "s3_url": graph_payload.get("url")
                        }

                    # Optional safety fallback (can remove later if confident)
                    elif isinstance(graph_payload, (Figure, go.Figure)):
                        logger.info("on_message: case where graph_payload is already a Figure object")
                        elements.append(
                            cl.Plotly(
                                name="chart",
                                figure=graph_payload,
                                display="inline",
                                size="large"
                            )
                        )
                        graph_meta = {"graph": "figure_object"}

                elif isinstance(result, dict) and 'graph_data' in result:
                    graph_data = result.get('graph_data')
                    if isinstance(graph_data, dict) and "url" in graph_data and "objectKey" in graph_data:
                        logger.info("on_message: case where graph_data is a dict with S3 metadata")
                        fig = await _fig_from_url(graph_data["url"])
                        elements.append(cl.Plotly(name="chart", figure=fig, display="inline", size="large"))
                        graph_meta = {"graph_data": graph_data, "s3_object_key": graph_data.get("objectKey"), "s3_url": graph_data.get("url")}
                    elif isinstance(graph_data, dict):
                        logger.info("on_message: case where graph_data is a dict that may represent a figure")
                        fig = Figure.from_dict(graph_data)
                        elements.append(cl.Plotly(name="chart", figure=fig, display="inline", size="large"))
                        graph_meta = {"graph_data": "figure_dict"}
                    elif isinstance(graph_data, str):
                        try:
                            logger.info("on_message: case where graph_data is a string that may be JSON for a figure")
                            fig = go.Figure(pio.from_json(graph_data))
                            elements.append(cl.Plotly(name="chart", figure=fig, display="inline", size="large"))
                            graph_meta = {"graph_data": "json_string"}
                        except Exception:
                            if is_base64_png(graph_data):
                                logger.info("on_message: case where graph_data is a base64-encoded PNG string")
                                elements.append(cl.Image(name="matplotlib_chart", content=graph_data, mime_type="image/png"))
                                graph_meta = {"graph_data": "png_base64"}
                            elif len(graph_data) > 1000:
                                try:
                                    logger.info("on_message: case where graph_data is a long string that may be a compressed Plotly figure")
                                    fig = await decode_plotly_figure(graph_data)
                                    elements.append(cl.Plotly(name="chart", figure=fig, display="inline", size="large"))
                                    graph_meta = {"graph_data": "decoded_base64"}
                                except Exception:
                                    logger.exception("Failed to decode large string graph_data")
                            else:
                                logger.exception("Unsupported graph_data string format")


                elif isinstance(result, dict) and 'graph_path' in result:
                    logger.info("on_message: plotly figure is saved as JSON and only path graph_path is sent") 
                    graph_path = result['graph_path']
                    try:
                        with open(graph_path) as f:
                            fig = go.Figure(pio.from_json(f.read()))
                            logger.info(f"Read JSON figure and converted to Plotly {type(fig)}")
                            elements.append(cl.Plotly(name="viewer", figure=fig, display="inline", size="large"))
                    except Exception as e:
                        logger.debug(f"Rendering Plotly viewer failed! Error {str(e)}")
                        raise

                elif 'elements' in result and result['elements']:
                    try:
                        for i in result['elements']:
                            if isinstance(i, MolView):
                                mol_view = cl.CustomElement(
                                    name="MolView",
                                    props={
                                        "cid": i.cid,
                                        "regno": i.regno,
                                        "title": i.title,
                                        "mode": i.mode,
                                        "bg": i.bg
                                    }
                                )
                                logger.info(f"CustomElement produced: props={mol_view.props}")
                                elements.append(mol_view)
                    except Exception:
                        logger.exception("Error while rendering Molecule View.")
                        await cl.Message(content="Molecule view could not be rendered.").send()
            except Exception:
                logger.exception("Error while preparing graph elements from workflow result")

            #await cl.Message(content=response, elements=elements).send()

            logger.info(f"Prepared {len(elements)} elements for Chainlit message. Graph metadata: {graph_meta}")

            # Extract assistant text robustly
            assistant_text = ""
            try:
                if isinstance(result, dict):
                    resp = result.get("processed_response") or result.get("response", "")
                    if isinstance(resp, dict):
                        assistant_text = resp.get("content") or resp.get("text") or ""
                    else:
                        assistant_text = str(resp) if resp is not None else ""
                else:
                    assistant_text = str(result) if result is not None else ""
            except Exception:
                assistant_text = str(result) if result is not None else ""

            # Sanitize assistant_text to remove embedded JSON/code blocks so the UI doesn't show Plotly JSON
            try:
                if assistant_text and hasattr(wf, "_sanitize_assistant_content"):
                    assistant_text = wf._sanitize_assistant_content(assistant_text)
            except Exception:
                # fallback: ensure it's a short string
                assistant_text = (assistant_text or "").strip()

            # If nothing to show (no text and no elements) send default error
            if (not assistant_text or not assistant_text.strip()) and not elements:
                # clear running flag before early return
                cl.user_session.set("running", False)
                await cl.Message(content=wf.default_error_msg.content).send()
                return

            # Build and send message
            if assistant_text and assistant_text.strip():
                msg = cl.Message(content=f"{assistant_text.strip()}\n\n---\n\n", elements=elements)
            else:
                msg = cl.Message(content="", elements=elements)

            logger.info(f"Sending Chainlit message with content length {len(assistant_text)} and {len(elements)} elements.")
            msg.metadata = graph_meta or {}
            await msg.send()
            ########################Chat GPT suggestion ############################
            try:
                thread_id = cl.user_session.get("thread_id")
                if thread_id and msg.metadata:
                    thread = await cl.data_layer.get_thread(thread_id)
                    meta = thread.get("metadata", {}) or {}

                    plots_map = meta.get("plots_by_message", {})

                    # IMPORTANT: use message ID
                    plots_map[str(msg.id)] = msg.metadata

                    meta["plots_by_message"] = plots_map

                    await cl.data_layer.update_thread(thread_id, metadata=meta)

                    logger.info(f"Persisted plot metadata for message {msg.id}")

            except Exception:
                logger.exception("Failed to persist plot metadata")                                                                            
            ########################################################################
            # clear running flag now that the response was sent
            cl.user_session.set("running", False)
            logger.info("[REHYDRATION] Stored graph metadata for persistence: %s", msg.metadata)

        except Exception as e:
            logger.exception(f"Error processing query: {type(e).__name__}: {str(e)}")
            if loader_state['sent']: 
                cl.user_session.set("loader_state", 
                                        await update_loader_message(loader_msg, loader_state, loader_id, remove=True)
                )
            # Retrieve handler from session (may not exist if error occurred before handler creation)
            handler = cl.user_session.get("handler")
            if handler:
                try:
                    await handler.cancel_run()
                    logger.debug("Handler successfully canceled.")
                except Exception as e: 
                    logger.exception(f"Could not cancel handler: {str(e)}")

            # Attempt to remove stored TaskList from the session (if any)
            stored_tasklist = cl.user_session.get('tasklist')
            if stored_tasklist:
                try:
                    await stored_tasklist.remove()
                    logger.debug("TaskList successfully removed")
                except Exception as e:
                    logger.exception(f"Could not remove TaskList: {str(e)}")
                finally:
                    cl.user_session.set('tasklist', None)

            # Append the failed exchange to message_history so subsequent
            # runs have complete conversation context
            try:
                await wf.append_to_history(ctx, message.content)
            except Exception as hist_err:
                logger.debug(f"Failed to update message_history in error handler: {hist_err}")

            # Create a fresh Context to clear stale events while preserving store data
            try:
                old_state = await ctx.store.get_state()
                ctx = Context(wf)
                await ctx.store.set_state(old_state)
                cl.user_session.set("ctx", ctx)
                logger.info("Created fresh Context after error, preserved store state.")
            except Exception as ctx_err:
                logger.debug(f"Failed to reset context after error: {ctx_err}")

            # ensure running flag cleared on error
            cl.user_session.set("running", False)        
            await cl.Message(content=wf.default_error_msg.content).send()

        # ✅ Link plan to last sent message (at end of handler - thread data is available)
        thread_id = cl.user_session.get("thread_id")
        if thread_id:
            await link_plan_to_message(thread_id, "assistant_message")

@cl.on_chat_end
async def on_chat_end():
    thread_id = cl.user_session.get("thread_id") or getattr(cl.context.session, "thread_id", None)
    
    # Log user and thread info
    user_id = cl.user_session.get("user_id")
    if not user_id:
        u = cl.user_session.get("user")
        user_id = getattr(u, "identifier", None) if u else None
    logger.info(f"Chat end triggered • user={user_id} • thread={thread_id}")

    # Chainlit's disconnect handler auto-persists cl.user_session into thread
    # metadata right after this returns. Each successful turn in on_message
    # already refreshes serialized_ctx, so this is a top-up — error paths
    # leave the existing value in place rather than clobbering it.

    ctx = cl.user_session.get("ctx")
    if ctx is None:
        logger.warning(f"No Context found in session at chat end for • user={user_id} • thread={thread_id} - nothing to serialize")
        return

    try:
        # Snapshot memory into ctx.store before serialization so chat history survives
        wf = cl.user_session.get("wf")
        if wf is not None:
            try:
                await wf.flush_memory_to_context(ctx)
            except Exception as e:
                logger.warning(f"Failed to snapshot memory before serialization • user={user_id} • thread={thread_id}: {e}")

        ctx_dict = ctx.to_dict(serializer=JsonSerializer())
        cl.user_session.set("serialized_ctx", ctx_dict)
        logger.info(f"Serialized context saved • user={user_id} • thread={thread_id}")
    except ContextStateError:
        logger.warning(
            f"Workflow not running at chat end; skipping serialization • user={user_id} • thread={thread_id}"
        )
    except Exception as e:
        logger.exception(f"Failed to serialize workflow context on chat end for • user={user_id} • thread={thread_id}: {e}")
    

@cl.on_chat_resume
async def on_chat_resume():
    # Determine thread/user attempting to resume and log with thread id
    try:
        thread_id = getattr(cl.context.session, "thread_id", None)
    except Exception:
        thread_id = None
    # Reconstruct user_id for logging if available
    user_id = cl.user_session.get("user_id")
    if not user_id:
        u = cl.user_session.get("user")
        user_id = getattr(u, "identifier", None) if u else None
    logger.info(f"Resuming chat session • user={user_id} • thread={thread_id}")

    # ✅ Reinitialize data layers for resume
    data_layer_manager.configure_chainlit_layers()
    
    # Ensure feedback layer is available
    global feedback_layer
    if 'feedback_layer' not in globals() or feedback_layer is None:
        feedback_layer = data_layer_manager.get_feedback_layer()
    try:
        thread_id = cl.context.session.thread_id
        thread_data = await cl.data_layer.get_thread(thread_id) # ctx_dict = cl.user_session.get("serialized_ctx") might also work
        wf = await bioinsight_session(thread_id, presigned_s3_client=storage_provider)
        cl.user_session.set("wf", wf)

        ctx_dict = thread_data.get("metadata", {}).get("serialized_ctx", {})    
        if not ctx_dict:
            logger.info(f"No serialized context found in thread metadata for user={user_id} • thread={thread_id}; starting fresh workflow context")
            return

        ctx = Context.from_dict(workflow=wf, data=ctx_dict, serializer=JsonSerializer())
        cl.user_session.set("ctx", ctx)

        ############ ChatGPT suggestion ##############
        try:
            thread = await cl.data_layer.get_thread(thread_id)
            meta = thread.get("metadata", {}) or {}
            plots_map = meta.get("plots_by_message", {})

            for msg_id, entries in plots_map.items():
                if not entries:
                    continue

                # normalize to list
                if isinstance(entries, dict):
                    entries = [entries]

                elements = []

                for entry in entries:
                    url = entry.get("s3_url") or entry.get("url")
                    if not url:
                        continue

                    try:
                        fig = await _fig_from_url(url)
                        elements.append(
                            cl.Plotly(
                                name="chart",
                                figure=fig,
                                display="inline",
                                size="large"
                            )
                        )
                    except Exception:
                        logger.exception(f"Failed to rehydrate plot from {url}")

                if elements:
                    await cl.Message(content="", elements=elements).send()

            logger.info(f"Rehydrated plots for {len(plots_map)} messages")

        except Exception:
            logger.exception("Failed to rehydrate plots on resume")

        ##############################################
        # Restore memory from the snapshot saved during on_chat_end
        try:
            await wf.load_memory_from_context(ctx)
            memory_messages = await wf.memory.aget_all()
            total = len(memory_messages) if isinstance(memory_messages, list) else 0
            by_role = {}
            if isinstance(memory_messages, list):
                for m in memory_messages:
                    enum_role = m.role if hasattr(m, 'role') else 'unknown'
                    role = getattr(enum_role, 'value', None) or str(enum_role)
                    by_role[role] = by_role.get(role, 0) + 1

            if total:
                logger.info(f"Rehydrated context • user={user_id} • thread={thread_id} • memory restored • total={total} • by_role={by_role}")
            else:
                logger.info(f"Rehydrated context • user={user_id} • thread={thread_id} • no memory snapshot present")
        except Exception as e:
            logger.debug(f"Failed to restore memory from rehydrated ctx for • user={user_id} • thread={thread_id}: {e}")
    except Exception as e:
        logger.exception(f"Failed to resume and rehydrate workflow context for • user={user_id} • thread={thread_id}: {e}")

@cl.on_stop
async def on_stop():
    handler = cl.user_session.get("handler")
    wf = cl.user_session.get("wf")
    ctx = cl.user_session.get("ctx")
    query = cl.user_session.get("user_query")
    loader_state = cl.user_session.get("loader_state")
    tasklist =cl.user_session.get('tasklist')
    
    # remove loading bar
    if loader_state and loader_state['sent']:
        await loader_state['loader_msg'].remove()
    
    # cancel workflow run (use is_done() to avoid InvalidStateError from cancelled())
    if handler and not handler.is_done(): 
        await handler.cancel_run()
        
    if tasklist:
        await tasklist.remove()
    
    # remove chat message message from history if added
    if wf:
        try: 
            chat_history = await ctx.store.get("chat_history", [])
            if chat_history:
                last_message = chat_history[-1]
                if last_message.content == query: 
                    await ctx.store.set("chat_history", chat_history[:-1])
        except: 
            logger.warning("Unable to remove last message from memory.")

    cl.user_session.set("running", False)

    logger.info("Run stopped by user.")
    
@cl.on_feedback
async def on_feedback(feedback: cl_types.Feedback):
    """
    Main feedback handler for comprehensive feedback collection.
    
    This handler works within the constraints of the feedback context, which
    does not have access to cl.user_session data. It collects available data
    from the feedback object and conversation layer.
    """
    logger.info(f"Received feedback: {feedback.forId} with rating {feedback.value}")
    
    try:
        # Import the feedback processing functions
        from integrations.chainlit.on_feedback import process_feedback
        
        # Validate that feedback data layer is available
        if not feedback_layer:
            logger.error("Feedback data layer not available - cannot process feedback")
            return
        
        # Process the feedback using the feedback collection system
        success = await process_feedback(feedback, feedback_layer, cl.data_layer)
        
        if success:
            logger.info(f"✅ Feedback processed successfully for message {feedback.forId}")
        else:
            logger.warning(f"⚠️ Feedback processing completed with issues for message {feedback.forId}")
            
    except Exception as e:
        logger.error(f"❌ Critical error in feedback handler for message {feedback.forId}: {str(e)}")
        # Ensure the system continues to function even if feedback processing fails

# ✅ Handle logout action
@cl.action_callback("logout")
async def on_logout(action: cl.Action):
    user_id = cl.user_session.get("user_id")
    thread_id = cl.user_session.get("thread_id")
    user = cl.user_session.get("user")

    if user:
        logger.info(f"User {user_id} (thread={thread_id}) logged out.")
    else:
        logger.info("Logout requested but no active user in session.")

    # Clear everything from session
    cl.user_session.clear()

    await cl.Message(content="✅ You have been logged out. Please login again.").send()
    await cl.run_js("window.location.href='/login';")
    
@suggested_query_callback()
async def handle_suggested_query(action: cl.Action):
    """Handle a suggested query action by forwarding its payload query to `on_message`."""
    query = action.payload.get("query")
    await cl.Message(content=f"🔍 **Running query**: {query}").send()
    await on_message(cl.Message(content=query))

# 🔑 Reset session endpoint for logout → clears old Chainlit session
@fastapi_app.get("/reset-session")
async def reset_session(request: Request):
    logger.info("🔄 Resetting Chainlit user session")
    cl.user_session.clear()
    return {"status": "ok"}
