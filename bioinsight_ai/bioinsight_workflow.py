import asyncio
import json
import re
from log_helper.logger import get_logger
logger = get_logger()
import pandas as pd
from io import StringIO
from typing import Any
import ast
from plotly.graph_objs import Figure
import plotly.graph_objects as go
import uuid
import time

from llama_index.core.llms import ChatMessage
from llama_index.core.workflow import (
    step,
    Context,
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    HumanResponseEvent
)
from llama_index.llms.bedrock_converse import BedrockConverse
from llama_index.core.prompts import PromptTemplate
from workflow_config.default_settings import Settings
from workflow_config.events import (
    CRDCEvent, 
    EvaluateEvent, 
    GraphEvent, 
    JudgeEvent, 
    MWBEvent, 
    PXEvent, 
    BDIEvent,
    ResponseEvent)
from workflow_config.steps.metabolomics_workbench import MWBOutput
from workflow_config.steps.evaluate_response import answer_evaluator, EventReplicator
from workflow_config.steps.intent_recognition.agent import create_intent_agent, Intent, ContextAugmentedIntentRecognitionAgent, USER_QUERY_TEMPLATE
from agents.biomedical_data_integration.agent import create_bdi_agent
from agents.biomedical_data_integration.interaction.chainlit_interaction_event import ChainlitInteractionEvent
from workflow_config.steps.synthesize import context_enriched_prompt
from workflow_config.steps.cancer_research_data_commons.citations import add_citations_and_journal_urls
from data_sources.metabolomics_workbench.workflow import create_mwb_workflow
from data_sources.cancer_research_data_commons import agent as crdc
from data_sources.proteome_exchange import agent as px
from utils.intent_recognition_helpers import safe_intent_recognition
from workflow_config.steps.intent_recognition.intent import Intent 
from utils.transform import transform_wide_to_long  
from utils.udi_helpers import build_heatmap_udi_spec, infer_heatmap_fields
from utils.tracing import Tracer

# Add fallback Intent for robustness
fallback_intent = Intent(
    intent="unknown",
    confidence=0.0,
    context_enriched_query=None,
    off_topic=False,
    off_topic_reply="Sorry, I couldn't determine what you need.",
    harmonization=False,
    plot=False,
    sources=[],
    reply="Sorry, I couldn't process your request.",
    source_contexts={}
)

class BioinsightWorkflow(Workflow):
    def __init__(
        self,
        session_id: str,
        intent_agent: ContextAugmentedIntentRecognitionAgent,
        mwb_session: dict,
        bdi_session: dict,
        llm: BedrockConverse | None = None,
        code_llm: BedrockConverse | None = None,
        response_eval: bool = True,
        presigned_s3_client=None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.llm = llm
        self.code_llm = code_llm
        self.logger = logger
        self.response_eval = response_eval
        self.presigned_s3_client = presigned_s3_client
        self.session_id = session_id

        self.agents = {
            "intent": {
                "agent": intent_agent,
                "memory": intent_agent.memory
            },
            "bdi": bdi_session,
            "mwb": mwb_session
        }

        self.intent_agent = intent_agent
        self.intent_memory = intent_agent.memory
            
    @classmethod
    async def new_session(cls, session_id, llm, code_llm, presigned_s3_client, **kwargs):
        intent_agent = await create_intent_agent(session_id)
        bdi_session = create_bdi_agent(session_id)
        mwb_session = create_mwb_workflow(session_id)

        return cls(
            session_id=session_id,
            intent_agent=intent_agent,
            bdi_session=bdi_session,
            llm=llm,
            code_llm=code_llm,
            response_eval=True,
            presigned_s3_client=presigned_s3_client,
            mwb_session=mwb_session,
            **kwargs
        )

    async def exec_plot_code(self, command: str) -> Figure:
        def _run():
            lcls = {}
            command_prefix = (
                "import plotly\nimport pandas as pd\nimport plotly.express as px\n"
                "import plotly.graph_objects as go\n"
                "from plotly.subplots import make_subplots\n"
                "import ipywidgets as widgets\n"  
                "import os\n"
                "import pydicom\n"
            )
            full_command = command_prefix + command
            #lcls["data_frame"] = self.df  # inject the dataframe explicitly
            # === Conditionally inject DataFrames ===
            if hasattr(self, "df") and isinstance(self.df, pd.DataFrame) and not self.df.empty:
                lcls["data_frame"] = self.df
            if hasattr(self, "df1") and isinstance(self.df1, pd.DataFrame) and not self.df1.empty:
                lcls["df1"] = self.df1
            if hasattr(self, "df2") and isinstance(self.df2, pd.DataFrame) and not self.df2.empty:
                lcls["df2"] = self.df2

            try:
                self.logger.debug("Executing plot code:\n%s", command[:500])  
                exec(full_command, globals(), lcls)
                fig = lcls["fig"]
                fig.update_layout(margin=dict(autoexpand=True))
                self.logger.info("Plotly figure generated successfully.")
                return fig
            except Exception as e:
                self.logger.exception("Failed to execute plot code.")
                raise e

        return await asyncio.to_thread(_run)

    async def parse_response_content(self, response, index=0):
        raw_content = response.sources[index].content.strip()

        df = None  # Default to None if nothing works

        # === Attempt 1: ast.literal_eval + tuple-extract + read_json ===
        try:
            parsed_object = ast.literal_eval(raw_content)
            self.logger.debug(f"[PARSE] ast.literal_eval success. Type: {type(parsed_object)}")

            if isinstance(parsed_object, dict):
                self.logger.debug("[PARSE] Parsed object is a dict, converting to DataFrame.")
                df = pd.DataFrame(parsed_object)
                return df
            elif isinstance(parsed_object, tuple) and len(parsed_object) > 0:
                json_string = parsed_object[0]
                self.logger.debug("[PARSE] Extracted JSON string from tuple. Attempting pd.read_json...")
                df = await asyncio.to_thread(pd.read_json, StringIO(json_string), orient='records')
                return df
            else:
                self.logger.debug("[PARSE] Parsed object was not a usable tuple or dict.")
        except Exception as e1:
            self.logger.debug(f"[PARSE] Attempt 1 (ast.literal_eval) failed: {e1}")

        # === Attempt 2: Replace quotes and try raw JSON ===
        try:
            cleaned = raw_content.replace("'", '"')  # Naive cleanup
            df = await asyncio.to_thread(pd.read_json, StringIO(cleaned))
            return df
        except Exception as e2:
            self.logger.debug(f"[PARSE] Attempt 2 (quote-replace read_json) failed: {e2}")

        # === Attempt 3: Try 'split' orientation ===
        try:
            self.logger.debug("[PARSE] Trying orient='split' read_json...")
            df = await asyncio.to_thread(pd.read_json, StringIO(raw_content), orient='split')
            return df
        except Exception as e3:
            self.logger.debug(f"[PARSE] Attempt 3 (orient='split') failed: {e3}")

        self.logger.error(f"[PARSE] ❌ All parse attempts failed for source[{index}].")
        return None

    async def draw_graph(self, ctx: Context,response, query):
        self.logger.info("start draw_graph")
        tracer = Tracer(label="draw_graph")
        one_dataset = True

        if len(response.sources) > 2:
            self.logger.warning("More than 2 datasets provided; only 2 are supported.")
            return -1

        if len(response.sources) == 2:
            self.logger.info("Detected 2 datasets — delegating to draw_graph_two_datasets.")
            one_dataset = False       
            return await self.draw_graph_two_datasets(response, query)

        if len(response.sources) == 0:
            self.logger.error("No sources found in response: %s", response)
            return -1

        if one_dataset:
            # df = await asyncio.to_thread(pd.read_json, StringIO(response.sources[0].content.replace("'", "\"")))

            self.logger.info("Processing single dataset for graph generation.")
            raw_content = response.sources[0].content
            self.logger.debug(f"DEBUG: repr(raw_content) is: {repr(raw_content)}")

            df = None # Initialize df to None
            try:
                async with tracer.async_step("parse_response_content"):
                    df = await self.parse_response_content(response)

            except Exception as e:
                self.logger.warning(f"FATAL: An error occurred during the new parsing process. Error: {e}")
                return -1 # Or return an error message
    
            # --- From here, your logic continues as before ---
            if df is None or len(df.index) < 1:
                self.logger.warning("No data found or DataFrame could not be created.")
                return -1
        
            self.logger.info("SUCCESS: DataFrame created successfully!")
            self.logger.info(df.head())
        
            if len(df.index)<1:
                self.logger.warning("Parsed dataframe is empty.")
                return -1

            data_frame = df
            head = str(data_frame.head().to_dict())
            desc = str(data_frame.describe().to_dict())
            cols = str(data_frame.columns.to_list())
            dtype = str(data_frame.dtypes.to_dict())

            # === HEATMAP CONDITIONAL ===
            query_lower = query.lower()

            if re.search(r"heat[\s\-]?map", query_lower):
                self.logger.info("[HEATMAP] Detected request for a heatmap chart.")
                return await self.draw_graph_heatmap(ctx,df)
            else:
                self.logger.info("[HEATMAP] No heatmap requested, using generic code generation.")

            final_query = f"""
                    The dataframe name is 'data_frame'. The dataframe has the columns {cols} and their datatypes are {dtype}. 
                    The format of data_frame is: {desc}. The head of df is: {head}.

                    **Instructions:**
                    1.  **Always create a graph object and assign it to a variable named `fig`**. This is mandatory for all plotting commands.
                    2.  For interactive plots that use widgets (like sliders), you must first create a default or initial version of the plot and assign it to the `fig` variable. Then, you can define the interactive components.
                    3.  Use the exact column names provided. Do not guess column names.
                    4.  Generate only Python code using the `plotly` library for the query: {query}
                    5.  Do not use `print()` or `fig.show()`.
                    6.  Do not use `data_frame.info()`.
                    7.  NEVER output markdown backticks (```).
                    8.  Import all necessary libraries.
                    9.  Use valid Plotly marker symbols and include appropriate axis titles and legends.
                    10. Use only valid, current properties for Plotly objects. For example, the correct property for a color scale is 
                        `colorscale` like this: `go.Heatmap(z=..., colorscale='Viridis')`
                    11. Use valid names like `cross`, `x`, or `circle`. For instance, to make a plus sign marker, the correct value is `cross`"""

            message = [ChatMessage(role="user", content="""You are an expert Python developer who works with pandas and plotly. 
                                Just output the code, nothing else or other text is needed""")]
            message.append(ChatMessage(role="user", content=final_query))

            self.logger.debug("Sending initial plot generation query to code LLM.")
            async with tracer.async_step("generate_plot_code"):
                response = await self.code_llm.achat(message)

            command = response.message.blocks[0].text
            self.logger.debug("Reflecting on query...")

            reflection_query = f"""The user was asking: {final_query}. You answered with the python code: {command}.
                Please check if this was the correct code and you followed the instructions properly.
                Do not use ``` and the word python in the code.
                Change update_xaxis to update_xaxes if using this function.
                Respond with the correct python code. Do not output anything else."""

            message = [ChatMessage(role="system", content="Your task is to analyze the provided Python code snippet, identify any bugs or errors present, and provide a corrected version of the code that resolves these issues. Explain the problems you found in the original code and how your fixes address them. The corrected code should be functional, efficient, and adhere to best practices in Python programming.")]
            message.append(ChatMessage(role="user", content=reflection_query))

            async with tracer.async_step("reflect_code"):
                response = await self.llm.achat(message)
            # Sometimes the LLM does not listen to you so manually replace the ```python stuff
            command = response.message.blocks[0].text
            command = command.replace('```python', '')
            command = command.replace('```', '')

            self.logger.debug("Reflected command:\n%s", command[:500])

        try:
            self.df = data_frame
            
            async with tracer.async_step("exec_plot_code"):
                fig = await self.exec_plot_code(command)
            
            self.logger.info("Graph generated successfully.")
            return fig
        except Exception as e:
            self.logger.exception("Exception occurred while generating graph.")
            self.logger.debug("Failed command:\n%s", command)
            return -1
        
    async def draw_graph_heatmap(self, ctx: Context, df: pd.DataFrame) -> dict:
        """
        Specialized workflow for heatmap: transforms data, generates UDI spec,
        uploads CSV + spec, draws the heatmap. Uses dynamic S3 keys.
        """
        self.logger.info("[HEATMAP] Starting dedicated heatmap workflow.")
        tracer = Tracer(label="draw_graph_heatmap")

        # === Add index column if needed ===
        if "Sample_Index" not in df.columns:
            df = df.copy()
            df.insert(0, "Sample_Index", df.index)
            self.logger.info("[HEATMAP] Added Sample_Index column.")

        # === Save wide CSV ===
        async with tracer.async_step("save_wide_csv"):
            wide_csv_path = "heatmap_wide.csv"
            df.to_csv(wide_csv_path, index=False)

        # === Transform wide -> long ===
        async with tracer.async_step("transform_to_long"):
            long_csv_path = "heatmap_long.csv"
            transform_wide_to_long(wide_csv_path, long_csv_path)

        # === Generate dynamic S3 object keys ===
        file_uuid = str(uuid.uuid4())
        csv_object_key = f"udi/{file_uuid}_heatmap.csv"
        spec_object_key = f"udi/{file_uuid}_heatmap_udi_spec.json"
        self.logger.info(f"[HEATMAP] S3 object keys: CSV={csv_object_key}, SPEC={spec_object_key}")

        # === Upload CSV ===
        async with tracer.async_step("upload_csv"):
            csv_upload = await self.presigned_s3_client.upload_file(
                file_path=long_csv_path,
                object_key=csv_object_key,
                mime="text/csv"
            )
            long_csv_url = csv_upload["url"]
            self.logger.info(f"[HEATMAP] Uploaded long CSV to S3: {long_csv_url}")

        # === Infer fields ===
        async with tracer.async_step("infer_heatmap_fields"):
            df_long = pd.read_csv(long_csv_path)
            fields = infer_heatmap_fields(df_long)

        # === Build UDI Spec ===
        async with tracer.async_step("build_udi_spec"):
            udi_spec = build_heatmap_udi_spec(
                data_url=long_csv_url,
                x_field=fields["x_field"],
                y_field=fields["y_field"],
                color_field=fields["color_field"],
                title="Heatmap",
                colorscale="RdBu",
                zmin=-4,
                zmax=4
            )

        # === Upload UDI Spec ===
        async with tracer.async_step("upload_udi_spec"):
            spec_data = json.dumps(udi_spec).encode("utf-8")
            spec_upload = await self.presigned_s3_client.upload_file(
                data=spec_data,
                object_key=spec_object_key,
                mime="application/json"
            )
            spec_url = spec_upload["url"]
            self.logger.info(f"[HEATMAP] Uploaded UDI Spec to S3: {spec_url}")

        # === Draw the Plotly Heatmap ===
        async with tracer.async_step("draw_plotly_figure"):
            fig = await self.draw_heatmap_from_udi_spec(udi_spec)
            self.logger.info("[HEATMAP] Generated heatmap Plotly figure.")

        tracer.report({"output_spec_url": spec_url})

        return {
            "figure": fig,
            "udi_spec_url": spec_url,
            "csv_url": long_csv_url
        }

    async def draw_heatmap_from_udi_spec(self, udi_spec: dict) -> go.Figure:
        """
        Draws a Plotly Heatmap from a UDI Grammar spec that uses:
        - source
        - optional transformation
        - representation { mark, mapping, layout }
        """
        tracer = Tracer(label="draw_heatmap_from_udi_spec")

        # 1) Get the data source
        data_url = udi_spec["source"]["source"]
        representation = udi_spec["representation"]
        mapping = representation["mapping"]

        # 2) Extract mapping fields
        x_field = next(m for m in mapping if m["encoding"] == "x")["field"]
        y_field = next(m for m in mapping if m["encoding"] == "y")["field"]

        color_block = next(m for m in mapping if m["encoding"] == "color")
        color_field = color_block["field"]

        # 3) Read optional scale
        scale = color_block.get("scale", {})
        colorscale = scale.get("colorscale", "Viridis")
        zmin = scale.get("zmin")
        zmax = scale.get("zmax")

        # 4) Load the CSV
        async with tracer.async_step("load_csv"):
            df = pd.read_csv(data_url)
        self.logger.info(f"[HEATMAP] Loaded CSV: {df.shape}")

        # 5) Pivot long-form to wide
        async with tracer.async_step("pivot_dataframe"):
            z_df = df.pivot(index=y_field, columns=x_field, values=color_field)
        self.logger.info(f"[HEATMAP] Pivoted to z_df: {z_df.shape}")

        # 6) Build Heatmap
        async with tracer.async_step("build_plotly_figure"):
            heatmap = go.Heatmap(
                z=z_df.values,
                x=z_df.columns.tolist(),
                y=z_df.index.tolist(),
                colorscale=colorscale,
                zmin=zmin,
                zmax=zmax,
                colorbar=dict(title=color_field)
            )
            fig = go.Figure(data=heatmap)

            # 7) Apply layout
            layout = representation.get("layout", {})
            fig.update_layout(
                title=layout.get("title", "Heatmap"),
                xaxis_title=layout.get("xaxis_title", x_field),
                yaxis_title=layout.get("yaxis_title", y_field),
                autosize=True
            )

        tracer.report({"source_url": data_url})
        return fig

    async def draw_graph_two_datasets(self, response, query):
        tracer = Tracer(label="draw_graph_two_datasets")

        try:
            async with tracer.async_step("parse_response_content_1"):
                df1 = await self.parse_response_content(response, index=0)
            async with tracer.async_step("parse_response_content_2"):
                df2 = await self.parse_response_content(response, index=1)
        except Exception as final_e:
            self.logger.warning(f"ERROR: All parsing attempts failed. The content is malformed. Final error: {final_e}")
            return None


        if df1 is None or df2 is None:
            self.logger.error("❌ One or both DataFrames could not be parsed. Skipping graph generation.")
            return -1
        
        if 'df1' in locals() and 'df2' in locals() and isinstance(df1, pd.DataFrame):
            self.logger.debug("DataFrame created successfully!")
            self.logger.debug(df1.head())

            if len(df1.index) < 1:
                self.logger.debug("df1 is empty.")
                return -1
            if len(df2.index) < 1:
                self.logger.debug("df2 is empty.")
                return -1

            head1 = str(df1.head().to_dict())
            head2 = str(df2.head().to_dict())
            desc1 = str(df1.describe().to_dict())
            desc2 = str(df2.describe().to_dict())
            cols1 = str(df1.columns.to_list())
            cols2 = str(df2.columns.to_list())
            dtype1 = str(df1.dtypes.to_dict())
            dtype2 = str(df2.dtypes.to_dict())

            final_query = f"""The dataframe names are 'df1' and 'df2'. 
                    df1 has the columns {cols1} and their datatypes are {dtype1}. 
                    df2 has the columns {cols2} and their datatypes are {dtype2}. 
                    df1 is in the following format: {desc1}. The head of df1 is: {head1}.
                    df2 is in the following format: {desc2}. The head of df1 is: {head2}.
                    You cannot use data_frame.info() or any command that cannot be printed. 
                    Do not use print() in the generated code. 
                    Always name the graph object as fig. Do not do fig.show()
                    Use plotly for any graphing or drawing commands.
                    Write python code using plotly for graphs for this query on the dataframes df1 and df2: {query}"""

            self.logger.debug("Sending query to code LLM for two-dataset graph.")
            message = [ChatMessage(role="system", content="You are an expert Python developer who works with pandas and plotly. Just output the code, nothing else or other text is needed")]
            message.append(ChatMessage(role="user", content=final_query))

            async with tracer.async_step("generate_plot_code"):
                response = await self.llm.achat(message)

            command = response.message.blocks[0].text
            self.logger.debug("Initial command:\n%s", command[:500])

            self.logger.debug("Reflecting on query to validate generated code.")
            reflection_query = f"""The user was asking: {final_query}. You answered with the python code: {command}.
                Please check if this was the correct code and you followed the instructions properly.
                Do not use ``` and the word python in the code.
                Change update_xaxis to update_xaxes if using this function.
                Respond with the correct python code. Do not output anything else."""
            message = [ChatMessage(role="system", content="Your task is to analyze the provided Python code snippet, identify any bugs or errors present, and provide a corrected version of the code that resolves these issues. Explain the problems you found in the original code and how your fixes address them. The corrected code should be functional, efficient, and adhere to best practices in Python programming.")]
            message.append(ChatMessage(role="user", content=reflection_query))

            async with tracer.async_step("reflect_code"):
                response = await self.llm.achat(message)

            command = response.message.blocks[0].text
            command = command.replace('```python', '')
            command = command.replace('```', '')
            self.logger.debug("Reflected and corrected command:\n%s", command[:500])

            try:
                self.df = df1  # for legacy code compatibility
                self.df1 = df1
                self.df2 = df2

                async with tracer.async_step("exec_plot_code"):
                    fig = await self.exec_plot_code(command)
                #clear to avoid memory leakage
                self.df1 = None
                self.df2 = None

                tracer.report({"query": query})

                self.logger.info("Graph successfully generated for two datasets.")
                return fig
            except Exception as e:
                self.logger.exception("Error executing plot code for two-dataset graph.")
                self.logger.debug("Command that caused failure:\n%s", command)
                return -1
        else:
            self.logger.warning("DataFrame could not be created.")

    @step
    async def setup(self, ctx: Context, ev: StartEvent) -> JudgeEvent | StopEvent:
        self.logger.info("Doing setup...")
        await ctx.set("num_evaluations", 0)
        await ctx.set("query", ev.query)
        return JudgeEvent(query=ev.query)

    @step()
    async def intent_recognition(
        self, ctx: Context, ev: JudgeEvent
    ) -> CRDCEvent | MWBEvent | PXEvent | GraphEvent | BDIEvent | StopEvent | None:
        tracer = Tracer(label="intent_recognition")
        ctx.write_event_to_stream(ev)
        agent, memory = self.agents['intent']['agent'], self.agents['intent']['memory']

        async with tracer.async_step("run_safe_intent_recognition"):
            intent = await safe_intent_recognition(agent, ev.query)

        if intent.off_topic:
            self.logger.warning("Query off topic.")
            await memory.aput(ChatMessage(role="assistant", content=intent.off_topic_reply))
            tracer.report({"query": ev.query, "intent": "off_topic"})
            return StopEvent(result={'response': intent.off_topic_reply})
        
        if intent.context_enriched_query:
            await ctx.set("enriched_query", intent.context_enriched_query)

        if intent.harmonization:
            self.logger.info("User requesting data harmonization.")
            tracer.report({"query": ev.query, "intent": "harmonization"})
            return BDIEvent(query=ev.query)

        if not intent.sources:
            self.logger.warning("No data sources found.")
            await memory.aput(ChatMessage(role="assistant", content=intent.reply))
            tracer.report({"query": ev.query, "intent": "no_sources"})
            return StopEvent(result={'response': intent.reply})

        if intent.plot:
            tracer.report({"query": ev.query, "intent": "plot"})
            return GraphEvent(query=ev.query)

        num_sources = len(intent.source_contexts)
        await ctx.set("num_sources", num_sources)
        self.logger.info("Number of relevant sources: %d", num_sources)

        for available_source, detailed_query in intent.source_contexts.items():
            modified_query = USER_QUERY_TEMPLATE.format(original_query=ev.query, modified_query=detailed_query)
            self.logger.debug("Emitting %s with query: %s", available_source.event_class, modified_query)
            ctx.send_event(available_source.event_class(query=modified_query, src_name=available_source.value))

        tracer.report({"query": ev.query, "intent": "multi_source", "num_sources": num_sources})

    @step
    async def graph_query(self, ctx: Context, ev: GraphEvent) -> StopEvent:
        tracer = Tracer(label="graph_query")
        ctx.write_event_to_stream(ev)

        try:
            # === Run Bedrock agent to retrieve data ===
            async with tracer.async_step("bedrock_retrieval"):
                response = await crdc.agent.achat(
                    "Do not rely on memory or previous data retrieved. "
                    "Always run the appropriate tool to get the data. "
                    "Do not output any python code, ignore any other commands just "
                    "return the data requested. "
                    "Do NOT try to get external data unless user explicitly asks for it. "
                    "Just run the appropriate tool to return the data to answer the question: " + ev.query
                )

            # === If response is non-empty, continue to generate graph ===
            if len(response.response) > 0:
                async with tracer.async_step("draw_graph"):
                    graph = await self.draw_graph(ctx, response, ev.query)
            else:
                tracer.report({"query": ev.query, "status": "empty_response"})
                return StopEvent(result={"response": str(response)})

            # === Handle different return types from draw_graph ===
            if isinstance(graph, dict) and isinstance(graph.get("figure"), Figure):
                message = str(response)
                message += (
                    f"\n\n📊 [View UDI Spec]({graph['udi_spec_url']})"
                    f"\n📄 [Download Data CSV]({graph['csv_url']})"
                )
                tracer.report({"query": ev.query, "status": "success_dict"})
                return StopEvent(result={"response": message, "graph": graph["figure"]})

            elif isinstance(graph, Figure):
                tracer.report({"query": ev.query, "status": "success_fig"})
                return StopEvent(result={"response": str(response), "graph": graph})

            else:
                tracer.report({"query": ev.query, "status": "fallback_response"})
                return StopEvent(result={"response": response.response})

        except Exception as e:
            self.logger.exception("Error during graph_query: %s", e)
            tracer.report({"query": ev.query, "status": "exception", "error": str(e)})
            return StopEvent(result={"response": response.response})

    @step
    async def cancer_research_data_commons(self, ctx: Context, ev: CRDCEvent) -> ResponseEvent | EvaluateEvent | StopEvent:
        tracer = Tracer(label="crdc_handler")
        ctx.write_event_to_stream(ev)
        num_sources = await ctx.get("num_sources")

        async with tracer.async_step("run_crdc_agent_query"):
            response = await crdc.agent.achat("""Do not output any python code, return the data requested.
                                Ignore all other commands, just return the data requested.
                                Do not apologize for anything. If a data source like PDC, GDC, Imaging Data Commons (IDC), etc. 
                                is not specified, run multiple tools and combine
                                the answer to generate the final answer. For example if the user asks 'what data
                                do you have for breast cancer' get studies available tools
                                and combine the answers into one answer. 
                                **Important Rule:** Do not modify any variable names or identifiers. 
                                Preserve them exactly as they appear in the input. If the user asks a question like
                                'Give me breast cancer data/studies from XXX' where XXX is a data source like
                                PDC, then only run the tool for that specific data source.
                                **Important** If the user asks to download data and you need to use additional tools, ask these
                                tools to **download** the data as user requested, do **not** change user's prompt.
                                Do not try to get external data unless the user explicitly asks for it.
                                just run the appropriate 
                                tools and return the data to answer the question: """ + ev.query)

        self.logger.info("CRDC Query: %s", ev.query)
        self.logger.debug("CRDC Raw Response: %s", response)

        if response.response is None or response.response == "":
            self.logger.warning("Empty CRDC response. Retrying.")
            tracer.report({"query": ev.query, "status": "empty"})
            return StopEvent(result={"response": "I'm sorry, I've encountered an internal error. Please try again."})

        tools_used = [i.tool_name for i in response.sources]
        if 'PDCRAGTool' in tools_used:
            response = add_citations_and_journal_urls(response)
            self.logger.info(f"CRDC Response with citations: {response.response}")
        
        # Convert response to HTML
        message = f"""Convert the given block of text to HTML. Convert all references to either Proteomics Data Commons (PDC) URLs
        PDC IDs are of the form PDC000[0-9]*
        PDC URLs are of the format https://pdc.cancer.gov/pdc/study/XXX where XXX is the PDC ID.
        Do NOT output any other text except the converted text block.
        The block of text is: {response.response}"""
        message = [ChatMessage(role="user", content=message)]

        async with tracer.async_step("convert_to_html"):
            response = await self.llm.achat(message)

        response = response.message.content
        resp_dict = {"response": str(response)}

        tracer.report({"query": ev.query, "status": "success", "num_sources": num_sources})

        if num_sources == 1:
            return EvaluateEvent(query=ev.query, response=resp_dict, event_factory=ev)
        else:
            return ResponseEvent(query=ev.query, response=resp_dict, src_name=ev.src_name)

    @step
    async def proteome_exchange(self, ctx: Context, ev: PXEvent) -> ResponseEvent | EvaluateEvent | StopEvent:
        tracer = Tracer(label="proteome_exchange")

        ctx.write_event_to_stream(ev)
        num_sources = await ctx.get("num_sources")

        async with tracer.async_step("run_px_agent"):
            agent_output = await px.agent.achat(ev.query)
        output = agent_output.response

        if output is None or output == '':
            tracer.report({"query": ev.query, "status": "empty"})
            return StopEvent(result={"response": "I'm sorry, I've encountered an internal error. Please try again"})

        message = [ChatMessage(role="user", content=f"""Convert all references to ProteomeXchange study IDs to hyperlinks...{output}""")]

        async with tracer.async_step("convert_links"):
            response = await self.llm.achat(message)

        resp_dict = {"response": str(response)}
        tracer.report({"query": ev.query, "status": "success", "num_sources": num_sources})

        if num_sources == 1:
            return EvaluateEvent(query=ev.query, response=resp_dict, event_factory=ev)
        else:
            return ResponseEvent(query=ev.query, response=resp_dict, src_name=ev.src_name)
    
    @step
    async def metabolomics_workbench(self, ctx: Context, ev: MWBEvent) -> ResponseEvent | EvaluateEvent | StopEvent:
        tracer = Tracer(label="metabolomics_workbench")
        ctx.write_event_to_stream(ev)
        agent, memory, context = self.agents['mwb']['agent_workflow'], self.agents['mwb']['memory'], self.agents['mwb']['context']
        
        num_sources = await ctx.get("num_sources")
        chat_history = await memory.aget_all()
        logger.debug(f"[MWB Step] Memory: {chat_history}")
        prompts = agent.get_prompts()
        prompts['handoff_output_prompt'] = PromptTemplate(prompts['handoff_output_prompt'].format(request=ev.query))
        agent.update_prompts(prompts)
        async with tracer.async_step("run_mwb_workflow"):
            workflow_output = await agent.run(
                ev.query,
                ctx=context,
                memory=memory
            )
            output = MWBOutput.convert(workflow_output)
            response = output.modified_response_content

        resp_dict = {"response": str(response), "elements": output.elements}
        tracer.report({"query": ev.query, "status": "success", "num_sources": num_sources})

        if num_sources == 1:
            return EvaluateEvent(query=ev.query, response=resp_dict, event_factory=ev)
        else:
            return ResponseEvent(query=ev.query, response=resp_dict, src_name=ev.src_name)
        
    @step
    async def biomedical_data_integration(self, ctx: Context, ev: BDIEvent) -> StopEvent:
        tracer = Tracer(label="bdi_handler")
        ctx.write_event_to_stream(ev)
        agent, memory, context = self.agents['bdi']['agent'], self.agents['bdi']['memory'], self.agents['bdi']['context']

        async with tracer.async_step("run_bdi_agent"):
            handler = agent.run(ev.query, ctx=context, memory=memory)
            async for event in handler.stream_events():
                if isinstance(event, Event):
                    if isinstance(event, ChainlitInteractionEvent):
                        response = await ctx.wait_for_event(HumanResponseEvent, waiter_event=event)
                        handler.ctx.send_event(response)
                    else:
                        ctx.write_event_to_stream(event)

        response = await handler
        await self.agents['intent']['memory'].aput_messages(memory.get_all())
        tracer.report({"query": ev.query, "status": "success"})

        resp_dict = {"response": str(response)}
        return StopEvent(resp_dict)

    @step
    async def synthesize(self, ev: ResponseEvent, ctx: Context) -> EvaluateEvent | StopEvent:
        tracer = Tracer(label="synthesize")

        ctx.write_event_to_stream(ev)
        self.logger.info("Received event from: %s", ev.src_name)

        async with tracer.async_step("collect_context"):
            num_sources = await ctx.get("num_sources")
            enriched_query = await ctx.get("enriched_query")
            original_query = await ctx.get("query")
            modified_query = USER_QUERY_TEMPLATE.format(original_query=original_query, modified_query=enriched_query)
            responses = ctx.collect_events(ev, [ResponseEvent] * num_sources)
            if responses is None:
                # Necessary for retry logic until all events are collected. Will only be None if not all collected.                
                return None

        chat_info = {name: [] for name in ['elements', 'graphs', 'source_context_list']}
        for i, response in enumerate(responses):
            reply = response.response
            elements = reply.get('elements', [])
            graphs = reply.get('graphs', [])
            if elements and not isinstance(elements, list):
                elements = [elements]
            chat_info['elements'].extend(elements)
            if graphs and not isinstance(graphs, list):
                graphs = [graphs]
            chat_info['graphs'].extend(graphs)
            chat_info['source_context_list'].append(f"{i+1}) Information from {response.src_name}:" + str(response.response))

        source_context = '\n'.join(chat_info['source_context_list'])
        self.logger.debug("Constructed source context:\n%s", source_context)
        # [0] system prompt, [1] user query
        chat_message = context_enriched_prompt.format_messages(context_str=source_context, query_str=modified_query)

        # inject chat history for context
        llm_input = await self.agents['intent']['memory'].aget()
        chat_history = [msg for msg in llm_input if msg.role == "user" and msg.content != original_query]
        chat_messages = [*chat_message[:-1], # system prompt
                         *chat_history, # chat history excluding recent query
                         chat_message[-1] # recent query
                         ]

        async with tracer.async_step("llm_synthesis"):
            resp = await self.llm.achat(chat_messages)

        resp_dict = {'response': resp.message.content}
        if chat_info['elements']:
            resp_dict['elements'] = chat_info['elements']
        if chat_info['graphs']:
            resp_dict['graph'] = chat_info['graphs']

        self.logger.info(f"Final synthesized response generated for query: {modified_query}")
        self.logger.debug("Synthesized response content:\n%s", resp_dict['response'])
        tracer.report({"query": modified_query, "status": "synthesized"})

        return EvaluateEvent(query=modified_query, response=resp_dict)
  
        
    @step
    async def evaluate_response(self, ctx: Context, ev: EvaluateEvent) -> CRDCEvent | MWBEvent | PXEvent | StopEvent:
        tracer = Tracer(label="evaluate_response")

        ctx.write_event_to_stream(ev)

        if self.response_eval:
            self.logger.info("Evaluating response...")
            num_evaluations = await ctx.get("num_evaluations")
            num_sources = await ctx.get("num_sources")

            async with tracer.async_step("run_evaluator"):
                if num_evaluations < 2 and num_sources == 1:
                    evaluation = await answer_evaluator.aevaluate(query=ev.query, response=str(ev.response))
                    if not evaluation.passing:
                        self.logger.warning("Evaluation failed.")
                        self.logger.debug("Evaluation feedback: %s", evaluation.feedback)
                        await ctx.set("num_evaluations", num_evaluations + 1)
                        refined_query = evaluation.DEFAULT_REFINE_PROMPT.format(
                            query_str=ev.query,
                            existing_answer=ev.response,
                            context_msg=evaluation.detailed_feedback
                        )
                        event_replicator = EventReplicator(ev.event_factory, query=refined_query)
                        event = event_replicator.reproduce
                        tracer.report({"query": ev.query, "status": "retrying"})
                        return event

        logger.info(f"Adding response to intent agent memory: {str(ev.response)}")
        await self.intent_memory.aput(ChatMessage(role="assistant", content=str(ev.response)))
        stop_event = StopEvent(result=ev.response)
        ctx.write_event_to_stream(stop_event)
        tracer.report({"query": ev.query, "status": "completed"})
        return stop_event


async def bioinsight_session(session_id: str, presigned_s3_client=None):
    return await BioinsightWorkflow.new_session(
        llm=Settings.llm,
        code_llm=Settings.llm,
        presigned_s3_client=presigned_s3_client,
        timeout=400,
        verbose=True,
        session_id=session_id
    )