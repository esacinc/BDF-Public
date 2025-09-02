from llama_index.core.workflow import Event

class BadQueryEvent(Event):
    "Event for an ambiguous query that is either needs clarity or is out-of-scope."
    query: str

class CRDCEvent(Event):
    "Event to send query to CRDC agent."
    query: str

class GraphEvent(Event):
    "Event to produce a graph."
    query: str

class JudgeEvent(Event):
    "Intent recognition event"
    query: str

class MWBEvent(Event):
    "Event to send query to MWB agent."
    query: str

class PXEvent(Event):
    "Event to send query to PX agent."
    query: str
    
class BDIEvent(Event):
    "Event to send query to BDI harmonization agent."
    query: str

class ResponseEvent(Event):
    "Event to capture response from a data source agent/workflow."
    query: str
    response: str | dict
    src_name: str

class EvaluateEvent(Event):
    "Event to capture LLM response and store corresponding user query."
    query: str
    response: str | dict