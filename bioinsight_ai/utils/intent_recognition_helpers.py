import json
import logging
from typing import Optional
from pydantic import ValidationError
import time

from workflow_config.steps.intent_recognition.intent import Intent
from log_helper.logger import get_logger
logger = get_logger()

async def safe_intent_recognition(
    intent_agent,
    query: str,
    retries: int = 2,
    fallback_intent: Optional[Intent] = None,
) -> Intent:
    """
    Call  structured intent agent safely.
    Guarantees a Pydantic Intent or raise cleanly.
    """

    attempt = 0

    while attempt <= retries:
        try:
            logger.info(f"[IntentRecognition] Attempt {attempt+1}: Calling agent.achat...")
            logger.info(f"[DEBUG] agent type: {type(intent_agent)}")
            logger.info(f"[DEBUG] agent.achat: {intent_agent.achat}")

            start = time.time()
            raw_response = await intent_agent.achat(query)
            duration = time.time() - start
            logger.info(f"[TIMER] Intent agent.achat call took {duration:.2f}s")

            logger.info(f"[IntentRecognition] Raw response: {raw_response}")
            logger.info(f"[IntentRecognition] Raw response type: {type(raw_response)}")

            if hasattr(raw_response, "model_dump"):
                logger.info("[IntentRecognition] Response is already a Pydantic Intent.")
                return raw_response

            if isinstance(raw_response, str):
                # Try to parse string as JSON
                logger.info("[IntentRecognition] Attempting to parse str as JSON...")
                raw_dict = json.loads(raw_response)
                intent_obj = Intent(**raw_dict)
                logger.info(f"[IntentRecognition] Parsed Intent: {intent_obj}")
                return intent_obj

            raise TypeError(
                f"[IntentRecognition] Unexpected response type: {type(raw_response)}. Value: {raw_response}"
            )

        except (json.JSONDecodeError, ValidationError, TypeError, AttributeError) as e:
            logger.warning(f"[IntentRecognition] Parse failed on attempt {attempt+1}: {e}")
            attempt += 1

    if fallback_intent:
        logger.error("[IntentRecognition] Returning fallback Intent after retries.")
        return fallback_intent

    raise RuntimeError(
        f"[IntentRecognition] Failed to parse Intent after {retries+1} attempts and no fallback provided."
    )
