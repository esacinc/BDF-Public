"""
Module: processed_workflow_handler

This module defines the `ProcessedWorkflowHandler` class, which serves as a wrapper for the `WorkflowHandler` class. 
It was created to enable post-processing of the `AgentOutput` returned by workflows, transforming it into a `ProcessedOutput` 
object while maintaining the existing interface and functionality of the `run` method.

### Problem Solved:
In workflows, the `run` method typically returns a `WorkflowHandler` that allows streaming intermediate events and 
awaiting the final result. However, there was a need to apply post-processing to the final result (e.g., converting 
`AgentOutput` to `ProcessedOutput`) without altering the existing interface or breaking compatibility with existing code. 
The `ProcessedWorkflowHandler` solves this by wrapping the `WorkflowHandler` and intercepting the final result to 
apply the necessary transformations.

### Key Features:
- Delegates all functionality to the original `WorkflowHandler`.
- Intercepts the final result when awaited and applies post-processing logic.
- Ensures compatibility with existing workflows and streaming functionality.
"""

class ProcessedWorkflowHandler:
    """
    A wrapper for WorkflowHandler to apply post-processing to the final result.

    This class intercepts the final result of the WorkflowHandler and applies a user-defined post-processing
    method (e.g., transforming `AgentOutput` into `ProcessedOutput`). It ensures that the interface and
    functionality of the original WorkflowHandler remain unchanged.
    """

    def __init__(self, handler, workflow):
        """
        Initialize the ProcessedWorkflowHandler.

        Args:
            handler: The original WorkflowHandler instance to wrap.
            workflow: The workflow instance containing the post-processing logic.
        """
        self._handler = handler
        self._workflow = workflow

    def __getattr__(self, name):
        """
        Delegate all other attributes to the original handler.

        Args:
            name (str): The name of the attribute to access.

        Returns:
            Any: The attribute value from the original handler.
        """
        return getattr(self._handler, name)

    def __await__(self):
        """
        Await the original handler and apply post-processing.

        Returns:
            ProcessedOutput: The post-processed result.
        """
        result = yield from self._handler.__await__()

        # Call the new post_run_agent_output hook on the workflow. This may
        # be synchronous or asynchronous; handle both.
        post_fn = getattr(self._workflow, "post_run_agent_output", None)
        if not callable(post_fn):
            wf_cls = type(self._workflow).__name__
            raise RuntimeError(f"Workflow class {wf_cls!r} does not implement post_run_agent_output method.")

        maybe = post_fn(result)
        if hasattr(maybe, "__await__"):
            return (yield from maybe.__await__())
        return maybe
