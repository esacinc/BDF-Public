from __future__ import annotations
from llama_index.core.evaluation import EvaluationResult, AnswerRelevancyEvaluator
from llama_index.core.prompts.default_prompts import DEFAULT_REFINE_PROMPT
from llama_index.core.prompts import PromptTemplate
from typing import Optional
from workflow_config.default_settings import Settings
import re

# From https://github.com/run-llama/llama_index/blob/27056ac2eb95a5d67e81a2583218a0fbc0d622c4/llama-index-core/llama_index/core/evaluation/answer_relevancy.py#L15
# Edited to allow for LLM clarifying responses and/or error.
evaluation_template = PromptTemplate(
    "Your task is to evaluate if the response is relevant to the query.\n"
    "The evaluation should be performed in a step-by-step manner by answering the following questions:\n"
    "1. Does the provided response match the subject matter of the user's query?\n"
    "2. Does the provided response attempt to address the focus or perspective "
    "on the subject matter taken on by the user's query?\n"
    "Each question above is worth 1 point. Provide detailed feedback on response according to the criteria questions above. "
    "After your feedback provide a final result by strictly following this format: '[RESULT] followed by the integer number representing the total score assigned to the response'\n\n"
    "Important: if the response is seeking clarification or provides detail about an error then assign [RESULT] to be the highest score possible (e.g. give one point for each of the above criteria questions). "
    "Query: \n {query}\n"
    "Response: \n {response}\n"
    "Feedback:"
)

#
# Evaluation classes
# 
class CustomEvalResult(EvaluationResult):
    detailed_feedback: Optional[str] = None
    passing: Optional[bool] = True
    DEFAULT_REFINE_PROMPT: Optional[PromptTemplate] = DEFAULT_REFINE_PROMPT
    
    # create CustomEvalResult from EvaluationResult and avoid overwriting child class with parent class attributes (passing specifically)
    @classmethod
    def from_evaluation_result(cls, evaluation_result: EvaluationResult) -> CustomEvalResult:
        instance = cls.model_validate(evaluation_result.model_dump(exclude={"passing"}))
        return instance

# Extend AnswerRelevancyEvaluator to define passing attribute and parse for detailed feedback
class QueryAnswered(AnswerRelevancyEvaluator):
    async def aevaluate(self, query=None, response=None, contexts=None, sleep_time_in_seconds=0, **kwargs):
        evaluation = await super().aevaluate(query, response, contexts, sleep_time_in_seconds, **kwargs)
        result = CustomEvalResult.from_evaluation_result(evaluation)
        if (result.score and result.score < 1.0):
            result.passing = False
            match = re.search(r'Detailed Feedback:\n(.*?)(?=\n\[RESULT\])', result.feedback, re.DOTALL)
            if match:
                result.detailed_feedback = match.group(1).strip()
        return result    

# Given an object this class returns an object of the same class. Any args are passed on to that class
class EventReplicator:
    def __init__(self, obj, **kwargs):
        self.original = obj
        self.cls = type(obj)
        self.reproduce = self.cls(**kwargs)
    
answer_evaluator = QueryAnswered(llm=Settings.fast_llm, eval_template=evaluation_template)