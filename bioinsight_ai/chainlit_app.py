import json

import boto3
import chainlit as cl
import chainlit.data as cl_data
from chainlit.input_widget import Select, Slider
from chainlit.data.dynamodb import DynamoDBDataLayer
from chainlit.data.storage_clients.s3 import S3StorageClient
from config import AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION, DATA_LAYER_TABLE, CHAINLIT_STORAGE_BUCKET
from bioinsight_workflow import bioinsight_session
import authentication
from plotly.graph_objs import Figure
import plotly.io as pio
import requests
import uuid
from storage.presigned_s3_client import PreSignedS3Client
from data_sources.metabolomics_workbench.mwb.chat_agent import MolView
from utils.chainlit_loader import update_loader_message
from workflow_config.events import (
    CRDCEvent, 
    MWBEvent, 
    PXEvent, 
    GraphEvent, 
    ResponseEvent, 
    EvaluateEvent)
from agents.biomedical_data_integration.interaction.chainlit_interaction_event import ChainlitInteractionEvent
from llama_index.core.workflow import HumanResponseEvent
from llama_index.core.agent.workflow.workflow_events import ToolCall, ToolCallResult, AgentStream
from log_helper.logger import get_logger
logger = get_logger()

# AWS Clients
logger.info("Initializing AWS DynamoDB and S3 clients.")
client = boto3.client(
    'dynamodb',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

storage_provider = PreSignedS3Client(
    bucket=CHAINLIT_STORAGE_BUCKET,
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    presigned_url_expiration=604800  # 7 days
)

cl_data._data_layer = DynamoDBDataLayer(
    table_name=DATA_LAYER_TABLE,
    client=client,
    storage_provider=storage_provider
)

@cl.on_chat_start
async def start():
    logger.info("Chat session started.")
    settings = await cl.ChatSettings(
        [
            Select(
                id="Model",
                label="LLM - Model",
                values=["Claude 3 Haiku", "Claude 3 Sonnet", "Llama 3.2 1B Instruct"],
                initial_index=0,
            ),
            Slider(
                id="Temperature",
                label="Temperature",
                initial=0.0,
                min=0.0,
                max=1.0,
                step=0.1,
            ),
            Slider(
                id="Token-Limit",
                label="Token Limit",
                initial=1,
                min=1,
                max=200000,
                step=1,
            )
        ]
    ).send()
    
    session_id = cl.user_session.get('id')
    logger.info(f"Starting session: {session_id}")
    wf = await bioinsight_session(session_id, presigned_s3_client=storage_provider)
    cl.user_session.set("wf", wf)

@cl.on_settings_update
async def setup_agent(settings):
    logger.info(f"Settings updated: {settings}")

@cl.on_message
async def on_message(message: cl.Message):
    if message.content:
        logger.info("Received message: %s", message.content)
        wf = cl.user_session.get("wf")

        if wf is None:
            logger.warning("Workflow not found in session.")
            await cl.Message(content="Workflow not found. Please refresh the session.").send()
            return

        try:
            logger.info("Running workflow...")
            # Initialize loader state
            loader_state = {
                "sent": False,
                "last_message": None
            }
            loader_id = str(uuid.uuid4())
            loader = cl.CustomElement(
                name="loader",
                id=loader_id,
                props={
            'message':"Thinking about your query..."
            })
            loader_msg = cl.Message(content="", elements=[loader])
            await loader_msg.send()
            loader_state['sent'] = True
            loader_state['last_message'] = loader_msg.content
            handler = wf.run(query=message.content)
            event_started = dict.fromkeys([
                "gathering_data",
                "creating_graph",
                "synthesizing_results",
                "evaluating_response"
                ], False)
            seen_agent_tools = set()
            async for event in handler.stream_events(): 
                if isinstance(event, (CRDCEvent, MWBEvent, PXEvent)) and not event_started["gathering_data"]:
                    event_started["gathering_data"] = True
                    await update_loader_message(loader_msg, loader_state, loader_id, "Gathering relevant information...")
                elif isinstance(event, GraphEvent) and not event_started["creating_graph"]: 
                    event_started["creating_graph"] = True
                    await update_loader_message(loader_msg, loader_state, loader_id, "Creating graph...")
                elif isinstance(event, ChainlitInteractionEvent):
                    await update_loader_message(loader_msg, loader_state, loader_id, remove=True)
                    try:
                        messages = event.build_chainlit_message()
                    except Exception as e:
                        logger.exception("Failed to build Chainlit message.")
                        continue

                    user_input = None

                    for msg in messages:
                        if isinstance(msg, cl.Message):
                            logger.info(f"Sending Message: {msg.content}")
                            await msg.send()
                        else:
                            try:
                                logger.info(f"Sending Ask* message: {msg.content}")
                                user_input = await msg.send()
                            except Exception as e:
                                logger.exception("Failed to send Ask* message.")
                                continue
                    if user_input is not None:
                        handler.ctx.send_event(HumanResponseEvent(response=user_input))
                    else:
                        logger.warning("No user input received from Ask* message.")
                elif isinstance(event, AgentStream):
                    for tool_call in event.tool_calls:
                        tool_id = tool_call.tool_id
                        tool_name = tool_call.tool_name
                        kwargs = tool_call.tool_kwargs

                        # Skip if we've already shown a message for this tool call
                        if tool_id in seen_agent_tools:
                            continue

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

                        # Determine message only when required args are present
                        message = None
                        if tool_name == "match_schema":
                            message = "Generating schema matches..."
                        elif tool_name == "rank_schema_matches" and kwargs.get("columns"):
                            message = f"Generating matches for {format_column_list(kwargs['columns'])}..."
                        elif tool_name == "process_schema_match_feedback" and kwargs.get("source_columns"):
                            message = f"Updating mapping for {format_column_list(kwargs['source_columns'])}..."
                        elif tool_name == "match_values" and kwargs.get("target_dataset_path"):
                            message = f"Generating value mappings for {kwargs['target_dataset_path']}..."
                        elif tool_name == "materialize_mapping":
                            message = "Harmonizing user dataset..."
                        elif tool_name == "return_data_to_user":
                            message = "Preparing dataset for download..."

                        # Show loader only if message is ready
                        if message:
                            await update_loader_message(loader_msg, loader_state, loader_id, message)
                            seen_agent_tools.add(tool_id)

                elif isinstance(event, ToolCall):
                    logger.info(
                        f"Using Tool: ({event.tool_name}):\n"
                        f"Arguments: {event.tool_kwargs}\n"
                    )
                elif isinstance(event, ToolCallResult) and not isinstance(event, ToolCall):
                    logger.info(
                        f"Tool Result ({event.tool_name}):\n"
                        f"Output: {event.tool_output}"
                        )
                    
                elif isinstance(event, ResponseEvent) and not event_started["synthesizing_results"]:
                    event_started["synthesizing_results"] = True
                    await update_loader_message(loader_msg, loader_state, loader_id, "Synthesizing results...")
                elif isinstance(event, EvaluateEvent) and not event_started["evaluating_response"]:
                    event_started["evaluating_response"] = True
                    await update_loader_message(loader_msg, loader_state, loader_id, "Evaluating response...")
                    
            result = await handler
            await update_loader_message(loader_msg, loader_state, loader_id, remove=True)
            logger.info("Workflow completed.")

            response = result.get("response", "No response found.")
            elements = []

            if 'graph' in result:
                graph_data = result['graph']
                try:
                    if isinstance(graph_data, dict):
                        fig = Figure.from_dict(graph_data)
                    elif isinstance(graph_data, str):
                        fig = pio.from_json(graph_data)
                    else:
                        fig = graph_data

                    elements.append(cl.Plotly(name="chart", figure=fig, display="inline", size="large"))
                except Exception:
                    logger.exception("Error while reconstructing Plotly chart.")
                    await cl.Message(content="Chart could not be rendered.").send()

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

            await cl.Message(content=response, elements=elements).send()

        except Exception:
            logger.exception("An unexpected error occurred while processing the query.")
            if loader_state['sent']: 
                await update_loader_message(loader_msg, loader_state, loader_id, remove=True)
            try:
                await handler.cancel_run()
                logger.debug("Handler successfully canceled.")
            except Exception as e: 
                logger.exception(f"Error canceling handler: {str(e)}")
            await cl.Message(content="An error occurred while processing your query.").send()

@cl.on_chat_resume
async def on_chat_resume():
    logger.info("Resuming chat session.")
    cl_data._data_layer = DynamoDBDataLayer(
        table_name=DATA_LAYER_TABLE,
        client=client,
        storage_provider=storage_provider
    )
    
    session_id = cl.user_session.get('id')
    wf = await bioinsight_session(session_id, presigned_s3_client=storage_provider)
    cl.user_session.set("wf", wf)