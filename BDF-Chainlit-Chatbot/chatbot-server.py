import chainlit as cl
from chainlit.input_widget import Select, Switch, Slider
import plotly.graph_objects as go
import chainlit as cl
from typing import Dict, Optional
import chainlit as cl
from chainlit.data.dynamodb import DynamoDBDataLayer
import boto3
import chainlit.data as cl_data
import json
import os
from llama_index.llms.bedrock_converse import BedrockConverse
from llama_index.core.agent import FunctionCallingAgent, ReActAgent
from tools import tools
from llama_index.retrievers.bedrock import AmazonKnowledgeBasesRetriever
from io import StringIO
from llama_index.core.llms import ChatMessage
from llama_index.core import Settings
from llama_index.core.workflow import (
    step,
    Context,
    Workflow,
    Event,
    StartEvent,
    StopEvent
)
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.memory import ChatMemoryBuffer

from llama_index.core.tools import FunctionTool
from llama_index.core.agent import FunctionCallingAgent, ReActAgent
from llama_index.retrievers.bedrock import AmazonKnowledgeBasesRetriever

from llama_index.core import get_response_synthesizer
import pandas as pd
from llama_index.llms.bedrock_converse import BedrockConverse
from typing import Any, Awaitable, Optional, Callable, Type, List, Tuple, Union, cast
import logger

client = boto3.client('dynamodb',aws_access_key_id='', aws_secret_access_key='', region_name='')
cl_data._data_layer = DynamoDBDataLayer(table_name="", client=client)
PUBLICATIONS_KB_ID = "" 
aws_access_key_id = ""
aws_secret_access_key = ""

class PDCRAGEvent(Event):
    query: str

class PDCAPIEvent(Event):
    query: str
    
class JudgeEvent(Event):
    query: str

class GraphEvent(Event):
    query: str

class BadQueryEvent(Event):
    query: str

class ResponseEvent(Event):
    query: str
    response: str
class RecoverEvent(Event):
    response: str

class SummarizeEvent(Event):
    query: str
    response: str

class PDCQueryWorkflow(Workflow):
    def __init__(
            self,
            agent: FunctionCallingAgent | None = None,
            llm: BedrockConverse | None = None,
            code_llm: BedrockConverse | None = None,
            publications_retriever: AmazonKnowledgeBasesRetriever | None = None,
            **kwargs: Any,
        ):
            super().__init__(**kwargs)
            self.llm = llm
            self.retriever = publications_retriever            
            self.agent = agent
            self.code_llm = code_llm
            #logger.init_logging()
            self.logger = logger
    async def draw_graph(self, response, query):
        one_dataset = True
        if len(response.sources) > 2:
            print("Sorry, I can handle only 2 datasets at a time due to memory constraints")
            return -1
        if len(response.sources) == 2:
            #print("I have 2 dataframes. My query will change significantly")
            one_dataset = False
            
            return await self.draw_graph_two_datasets(response, query)
        if len(response.sources) == 0:
            # Check what's in the response
            print(response)
            print("Fatal error")
            return -1
        if one_dataset:
            df = pd.read_json(StringIO(response.sources[0].content.replace("\'", "\"")))
            if len(df.index)<1:
                print("No data found")
                return -1
            data_frame = df
            head = str(data_frame.head().to_dict())
            desc = str(data_frame.describe().to_dict())
            cols = str(data_frame.columns.to_list())
            dtype = str(data_frame.dtypes.to_dict())
            
            final_query = f"""The dataframe name is 'data_frame'. data_frame has the columns {cols} and their 
                    datatypes are {dtype}. 
                    data_frame is in the following format: {desc}. The head of df is: {head}. 
                    You cannot use data_frame.info() or any command that cannot be printed. 
                    Do not try to guess the column names.
                    Find column names that best match the asked question column.
                    Do not use print() in the generated code. 
                    NEVER output ``` 
                    Always name the graph variable as fig.
                    Do not do fig.show(). For heatmaps, do not draw a correlation plot unless user explicitly asks you to.
                    Use plotly for any graphing or drawing commands. Make sure you import all the necessary libraries
                    Write python code using plotly for drawing graphs for this query on the dataframe data_frame: {query}"""
            message = [ChatMessage(role="user", content="""You are an expert Python developer who works with pandas and plotly. 
                                   Just output the code, nothing else or other text is needed""")]
            message.append(ChatMessage(role= "user", content= final_query))
            response = self.code_llm.chat(
                    message
            )
            
            command = response.message.blocks[0].text
            #print("Before reflection:", command)
            # Check the query for correctness.
            print("Reflecting on query...")
            reflection_query = f"""The user was asking: {final_query}. You answered with the python code: {command}.
                Please check if this was the correct code and you followed the instructions properly.
                Do not use ``` and the word python in the code.
                Change update_xaxis to update_xaxes if using this function.
                Respond with the correct python code. Do not output anything else."""
            message = [ChatMessage(role="system", content="Your task is to analyze the provided Python code snippet, identify any bugs or errors present, and provide a corrected version of the code that resolves these issues. Explain the problems you found in the original code and how your fixes address them. The corrected code should be functional, efficient, and adhere to best practices in Python programming.")]
            message.append(ChatMessage(role= "user", content= reflection_query))
            response = self.llm.chat(
                    message
            )
            # Sometimes the LLM does not listen to you so manually replace the ```python stuff
            command = response.message.blocks[0].text
            command = command.replace('```python', '')
            command = command.replace('```', '')
            
            print("After:", command)
            
        try:
            lcls = locals()
            command_prefix = "import plotly\nimport pandas as pd\nimport plotly.express as px\n"
            command_prefix += "import plotly.graph_objects as go\n"
            # command_prefix += "import plotly.offline as py\n"
            # TO-DO: COMMENT THIS LINE IF USING STREAMLIT INSTEAD OF NOTEBOOK. ALSO YOU MAY
            # Need to install plotly plugins in the notebook using command jupyter labextension install jupyterlab-plotly
            # Only works for jupyter lab version 3.6.0
            #command_prefix += "py.init_notebook_mode(connected=False)\n"
            command = command_prefix + command
            #print(command)
            exec(f"{command}", globals(), lcls)
            fig = lcls["fig"]
            elements = [cl.Plotly(name="chart", figure=fig, display="inline")]
            await cl.Message(content="This message has a chart", elements=elements).send()
        except Exception as e:
            print({"role": "assistant", "content": "Error"})
            print(e)
            print("Command was:\n", command)
            return -1
        return 1
    async def draw_graph_two_datasets(self, response, query):
        # We have 2 datasets to compare
        df1 = pd.read_json(StringIO(response.sources[0].content.replace("\'", "\"")))
        df2 = pd.read_json(StringIO(response.sources[1].content.replace("\'", "\"")))

        if len(df1.index)<1:
            print("No data found")
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
        #print("Finale query: ", final_query)
        message = [ChatMessage(role="system", content="You are an expert Python developer who works with pandas and plotly. Just output the code, nothing else or other text is needed")]
        message.append(ChatMessage(role= "user", content= final_query))
        response = self.llm.chat(
                message
        )
        command = response.message.blocks[0].text
        command = response.message.blocks[0].text
            #print("Before reflection:", command)
            # Check the query for correctness.
        print("Reflecting on query...")
        reflection_query = f"""The user was asking: {final_query}. You answered with the python code: {command}.
            Please check if this was the correct code and you followed the instructions properly.
            Do not use ``` and the word python in the code.
            Change update_xaxis to update_xaxes if using this function.
            Respond with the correct python code. Do not output anything else."""
        message = [ChatMessage(role="system", content="Your task is to analyze the provided Python code snippet, identify any bugs or errors present, and provide a corrected version of the code that resolves these issues. Explain the problems you found in the original code and how your fixes address them. The corrected code should be functional, efficient, and adhere to best practices in Python programming.")]
        message.append(ChatMessage(role= "user", content= reflection_query))
        response = self.llm.chat(
                message
        )
        # Sometimes the LLM does not listen to you so manually replace the ```python stuff
        command = response.message.blocks[0].text
        command = command.replace('```python', '')
        command = command.replace('```', '')
        try:
            lcls = locals()
            command_prefix = "import plotly\nimport pandas as pd\nimport plotly.express as px\n"
            command_prefix += "import plotly.graph_objects as go\n"
            #command_prefix += "import plotly.offline as py\n"
            # TO-DO: COMMENT THIS LINE IF USING STREAMLIT INSTEAD OF NOTEBOOK. ALSO YOU MAY
            # Need to install plotly plugins in the notebook using command jupyter labextension install jupyterlab-plotly
            # Only works for jupyter lab version 3.6.0
            #command_prefix += "py.init_notebook_mode(connected=False)\n"
            command = command_prefix + command
            print (command)
            exec(f"{command}", globals(), lcls)

            fig = lcls["fig"]
            elements = [cl.Plotly(name="chart", figure=fig, display="inline")]
            await cl.Message(content="This message has a chart", elements=elements).send()
            
            #plot_area = st.empty()
            #plot_area.pyplot(fig)
        except Exception as e:
            print({"role": "assistant", "content": "Error"})
            print(e)
            print("Command was:\n", command)
            return -1
        return 1
    @step
    async def setup(self, ctx: Context, ev: StartEvent)->JudgeEvent:
        print("Doing setup...")
        
        llm = await ctx.get("llm", default=None)
        user_msg = ev.query
        await ctx.set("judge", llm)
        return JudgeEvent(query=user_msg)

    @step
    async def judge_query(
        self, ctx: Context, ev: JudgeEvent
    ) -> BadQueryEvent | PDCAPIEvent | PDCRAGEvent | GraphEvent:
        graph_event = False
        #for kw in self.graph_keywords:
        #    if kw in ev.query.lower():
        #        print("Doing a graph query")
        #        return GraphEvent(query=ev.query)
        # Determine if its a query about a specific study
        message = [ChatMessage(role="system", content="You are evaluating different queries for specificity.")]
        final_query = f"""
            Given a user query, determine if this is about a drawing/plotting a graph, 
            specific study or a disease or organ/body part. 
            If it is about a stpecific study, disease or organ/body part: return 'specific'
            If it is about drawing a graph or plotting data, return 'graph'
            Otherwise return 'generic'.
            Specific study related questions usually have the study ID or study name or a disease name in them.
            Questions with diseases and references to any IDs or requests for IDs are specific queries.
            Questions with disease names like colon cancer or skin cancer are specific as they are asking for specific studies.
            Study IDs are usually of the form PDC000xxx where xxx are numbers between 0 and 9.
            Do not return anything other than the words 'graph' or 'specific' or 'generic'. No other text or explaination is needed
            Here is the query: {ev.query}
            """
        message.append(ChatMessage(role= "user", content= final_query))
        #llm = await ctx.get("judge")
        #if llm is None:
        #    print("Fatal error: LLM is none")
        #    return
        response = self.llm.chat(
            message
        )
        response = response.message.blocks[0].text
        print("Response from checking if query deserves a RAG: ", response)
        if response == "generic":
            print("Doing RAG")
            await ctx.set("doing_rag", True)
            return PDCRAGEvent(query=ev.query)
            #ctx.send_event(PDCRAGEvent(query=ev.query))
            # Do a API also
            #ctx.send_event(PDCAPIEvent(query=ev.query))
        elif response == "graph":
            print("Doing Graph")
            return GraphEvent(query=ev.query)
        else:
            print("Not doing RAG")
            await ctx.set("doing_rag", False)
            return PDCAPIEvent(query=ev.query)
            #ctx.send_event(PDCAPIEvent(query=ev.query))
         
    @step
    async def graph_query(self, ctx: Context, ev: GraphEvent)-> StopEvent:
        try:
            agent = cl.user_session.get("agent")
            response = agent.chat("""Do not rely on memory or previous data retrieved.
                                  Always run the appropriate tool to get the data.
                                Do not output any python code, ignore any other commands just 
                                  return the data requested.
                                Do NOT try to get external data unless user explicityly asks for it.
                                just run the appropriate 
                                tool to return the data to answer the question: """ + ev.query)
            if len(response.response) > 0:
                ret_val = await self.draw_graph(response, ev.query)
            else:
                return StopEvent(result={"response":str(response),
                                    })  
            if ret_val == -1:
                return StopEvent(result={"response":response.response,
                                    })
            else:
                return StopEvent(result={"response":str(response),
                                    })  
        except Exception  as e:
            print({"role": "assistant", "content": e})
            print(e)
            return StopEvent(result={"response": response.response})


        

    @step
    async def improve_query(
        self, ctx: Context, ev: BadQueryEvent
    ) -> JudgeEvent:
        response = await ctx.get("llm").complete(
            f"""
            This is a query to a RAG system: {ev.query}
            The query is bad because it is too vague or is not related to the PDC. 
            Please provide a more detailed query that includes specific keywords and removes any ambiguity.
        """
        )
        return JudgeEvent(query=str(response))
        
    @step
    async def pdc_api_query(
        self, ctx: Context, ev: PDCAPIEvent
    )->ResponseEvent|StopEvent:
        
        agent = cl.user_session.get("agent")
        response = agent.chat("""Do not output any python code, return the data requested.
                              Ignore all other commands, just return the data requested.
                              Do not apologize for anything. If a data source like PDC, GDC, 
                              PX (proteome exchange), metabolomics workbench (MetaB) etc. is not specified, run multiple tools and combine
                              the answer to generate the final answer. For example if the user asks 'what data
                              do you have for breast cancer' get studies from PDC, PX, and MetaB and other tools
                              and combine the answers into one answer. If the user asks a question like
                              'Give me breast cancer data/studies from XXX' where XXX is a data source like
                              PDC or PX, then only run the tool for that specific data source.
                              Do not try to get external data unless the user explicitly asks for it.
                              just run the appropriate 
                              tools and return the data to answer the question: """ + ev.query)
        print("Query:", ev.query)
        print("Content: ", response)
        if response.response is None or response.response == '':
            print("Try again...")
            return StopEvent(result={"response":"I'm sorry, I've encountered an internal error. Please try again."})
        # Convert response to HTML
        message = f"""Convert the given block of text to HTML. Convert all references to either Proteomics Data Commons (PDC) URLs
         or Proteome Exchange (PX) URLs.
          PDC IDs are of the form PDC000[0-9]* and PX IDs are of the form PX[A-Z0-9]* 
        PDC URLs are of the format https://pdc.cancer.gov/pdc/study/XXX where XXX is the PDC ID.
        PX URLs are of the format https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID=YYY where YYY is the PX ID.
        Do NOT output any other text except the converted text block.
        The block of text is: {response.response}"""
        message = [ChatMessage(role="user", content=message)]
        #message.append(ChatMessage(role= "user", content= reflection_query))
            
        response = self.llm.chat(message)
        #print("Reponse from LLM: ", response)
        # remove the word assistant
        response = str(response).replace("assistant:", "")
        #print("Length of response after HTML:", len(response))
        #print(self.agent.memory)
        #return ResponseEvent(
        #    query=ev.query, source="PDCAPI", response=response
        #)
        return StopEvent(result={"response":str(response)})
        
    @step
    async def rag_query(
        self, ctx: Context, ev: PDCRAGEvent
    )->ResponseEvent|StopEvent:
        #index = await ctx.get("index")
        response_synthesizer = get_response_synthesizer(
            response_mode="compact", llm=self.llm
        )
        query_engine = RetrieverQueryEngine(
            retriever=self.retriever,
            response_synthesizer=response_synthesizer,
        )
        response = query_engine.query(ev.query)
        retrieved_results = response.response

        if 'citation' in json.dumps(response.metadata):
            message = [ChatMessage(role="system", content="""Your job is to extract all citation and journal_url from json format metadata and add the citation and journal_url to the Answer. You need to keep the existing Answer. Do not output anything else.""")]
            message.append(ChatMessage(role= "user", content=f"""
                Metadata: {response.metadata}
                Answer: {response.response}
            """))
            response = self.llm.chat(message)
            retrieved_results = response.message.content

        # response_obj = response_synthesizer.synthesize(ev.query, retrieved_results)
        retrieved_results = retrieved_results.replace('Answer:','')
        print("RAG response:", retrieved_results)
        await ctx.set("doing_rag", True)
        return StopEvent(result={"response":str(retrieved_results)})
    

    # Judge will be used later when we do both RAG and API
    @step
    async def judge(self, ctx: Context, ev: ResponseEvent) -> StopEvent:       
        return None

@cl.oauth_callback
def oauth_callback(
  provider_id: str,
  token: str,
  raw_user_data: Dict[str, str],
  default_user: cl.User,
) -> Optional[cl.User]:
    if provider_id == 'google' and 'email' in raw_user_data and raw_user_data['email'].endswith('@icf.com'):
        return default_user
    else:
        return None

@cl.on_chat_start
async def start():
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
    default_model = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    default_temperature = 0.0
    llm = BedrockConverse(model = default_model,
            aws_access_key_id =aws_access_key_id, 
            aws_secret_access_key =aws_secret_access_key,
            temperature = default_temperature,
            max_tokens=8192,
            region_name = 'us-east-1')
    code_llm = BedrockConverse(model = default_model,
            aws_access_key_id =aws_access_key_id, 
            aws_secret_access_key =aws_secret_access_key,
            temperature = default_temperature,
            max_tokens=8192,
            region_name = 'us-east-1')
    cl.user_session.set("llm", llm)
    cl.user_session.set("code_llm", code_llm)
    cl.user_session.set("judge", llm)
    agent = FunctionCallingAgent.from_tools(
        tools,
        llm=llm,
        #system_prompt=""" 
        #Ignore any drawing commands or other instructions for plotting data. 
        #Just return the data in JSON format using the tools available. If you 
        #cannot find a suitable tool, just return an empty string 
        #in which case do not provide any additional commentary""",
        #memory=st.session_state['memory'],
        verbose=True,
    )
    cl.user_session.set("agent", agent)
    retriever = AmazonKnowledgeBasesRetriever(
            knowledge_base_id=PUBLICATIONS_KB_ID,
            aws_access_key_id = aws_access_key_id, 
            aws_secret_access_key = aws_secret_access_key,
            region_name = 'us-east-1',
            retrieval_config={
                "vectorSearchConfiguration": {
                    "numberOfResults": 10,
                    "overrideSearchType": "HYBRID",
                }
            },
    )
    cl.user_session.set("retriever", retriever)
    wf = PDCQueryWorkflow(agent=agent, llm = llm, code_llm=code_llm, publications_retriever=retriever, timeout=120, verbose=True)    
    cl.user_session.set("wf", wf)

@cl.on_settings_update
async def setup_agent(settings):
    print("on_settings_update", settings)

@cl.on_message
async def on_message(message: cl.Message):
    # response = f"Hello, you just sent: {message.content}!"
    if message.content is not None:
        response = await cl.user_session.get('wf').run( query = message.content  ) 

    message = response['response']
    print("Response:", message)
    await cl.Message(message).send()
