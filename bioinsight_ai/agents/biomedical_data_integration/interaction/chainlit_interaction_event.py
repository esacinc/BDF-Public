from typing import Literal, Dict, Any, List, Optional
from pydantic import Field, model_validator
import chainlit as cl
import logging
from llama_index.core.workflow import InputRequiredEvent

logger = logging.getLogger()

class ChainlitInteractionEvent(InputRequiredEvent):
    """
    Represents a Chainlit interaction that may include a visual message (with elements)
    followed by an interactive Ask* message that waits for a human response.
    """

    message_type: Literal["Message", "AskUserMessage", "AskFileMessage", "AskActionMessage"] = Field(
        ..., description="The primary Chainlit message type to render."
    )
    message_args: Dict[str, Any] = Field(
        ..., description="Arguments for the primary Chainlit message."
    )
    followup_type: Optional[Literal["AskUserMessage", "AskFileMessage", "AskActionMessage"]] = Field(
        None, description="Optional Ask* message type to follow a visual message."
    )
    followup_args: Optional[Dict[str, Any]] = Field(
        None, description="Arguments for the follow-up Ask* message."
    )

    @model_validator(mode="after")
    def validate_required_fields(self) -> "ChainlitInteractionEvent":
        """
        Ensure that 'content' exists in message_args.
        If message_type is 'Message', followup_type and followup_args must be provided.
        """
        if "content" not in self.message_args:
            logger.error("[CHAINLIT_INTERACTION_EVENT] Validation failed: 'content' is missing in message_args.")
            raise ValueError("`content` is required in `message_args` for all message types.")

        if self.message_type == "Message":
            if not self.followup_type or not self.followup_args:
                logger.error("[CHAINLIT_INTERACTION_EVENT] Validation failed: followup_type and followup_args are required when message_type is 'Message'.")
                raise ValueError("`followup_type` and `followup_args` are required when `message_type` is 'Message'.")
        return self

    def _build_elements(self, elements_data: List[Dict[str, Any]]) -> List[Any]:
        """
        Dynamically construct Chainlit UI elements from a list of dictionaries.
        Each dictionary must include a 'type' key that matches a Chainlit element class name.
        """
        built_elements = []
        for el in elements_data:
            el_type = el.pop("type")
            logger.debug(f"[CHAINLIT_INTERACTION_EVENT] Building element of type: {el_type}")
            try:
                ElementClass = getattr(cl, el_type)
            except AttributeError:
                logger.exception(f"[CHAINLIT_INTERACTION_EVENT] Unsupported element type: {el_type}")
                raise ValueError(f"Unsupported element type: {el_type}")
            built_elements.append(ElementClass(**el))
        logger.debug(f"Built {len(built_elements)} element(s).")
        return built_elements

    def _build_actions(self, actions_data: List[Dict[str, Any]]) -> List[cl.Action]:
        """
        Construct a list of Chainlit Action objects from dictionaries.
        """
        logger.debug(f"[CHAINLIT_INTERACTION_EVENT] Building {len(actions_data)} action(s).")
        return [cl.Action(**action) for action in actions_data]

    def build_chainlit_message(self) -> List[Any]:
        """
        Build one or two Chainlit messages:
        - A `cl.Message` with elements (if applicable)
        - Followed by an Ask* message that waits for user input
        """
        messages = []

        # Build the primary message
        args = self.message_args.copy()
        if self.message_type == "Message":
            logger.debug("[CHAINLIT_INTERACTION_EVENT] Building message...")
            if "elements" in args:
                args["elements"] = self._build_elements(args["elements"])
            messages.append(cl.Message(**args))

            # Build the follow-up Ask* message
            followup_args = self.followup_args.copy()
            if "actions" in followup_args:
                followup_args["actions"] = self._build_actions(followup_args["actions"])
            try:
                FollowupClass = getattr(cl, self.followup_type)
            except AttributeError:
                logger.exception(f"[CHAINLIT_INTERACTION_EVENT] Unsupported followup_type: {self.followup_type}")
                raise ValueError(f"Unsupported followup_type: {self.followup_type}")
            messages.append(FollowupClass(**followup_args))

        else:
            # Direct Ask* message (no visual message)
            if "actions" in args:
                args["actions"] = self._build_actions(args["actions"])
            try:
                AskClass = getattr(cl, self.message_type)
            except AttributeError:
                logger.exception(f"[CHAINLIT_INTERACTION_EVENT] Unsupported message_type: {self.message_type}")
                raise ValueError(f"Unsupported message_type: {self.message_type}")
            messages.append(AskClass(**args))

        logger.debug(f"[CHAINLIT_INTERACTION_EVENT] Built {len(messages)} message(s) for Chainlit interaction.")
        return messages
