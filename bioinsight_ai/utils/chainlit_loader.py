# loader_utils.py

import chainlit as cl

async def update_loader_message(loader_msg, loader_state, loader_id, new_message: str = "", remove: bool = False):
    """
    Update or remove the Chainlit loader message in a clean and state-aware way.

    Parameters:
    - loader_msg: The Chainlit message object containing the loader element.
    - loader_state (dict): A mutable dictionary tracking 'sent' and 'last_message' state.
    - loader_id (str): The unique ID of the loader element.
    - new_message (str): The message to display in the loader.
    - remove (bool): If True, removes the loader and resets state.

    Usage:
        await update_loader_message(loader_msg, loader_state, loader_id, "Loading...")
        await update_loader_message(loader_msg, loader_state, loader_id, remove=True)
    """
    if remove or not new_message:
        if loader_state["sent"]:
            await loader_msg.remove()
            loader_state["sent"] = False
            loader_state["last_message"] = None
        return

    if new_message == loader_state["last_message"] and loader_state["sent"]:
        return  # No update needed

    loader = cl.CustomElement(
        name="loader",
        id=loader_id,
        props={'message': new_message}
    )
    loader_msg.elements = [loader]

    if loader_state["sent"]:
        await loader_msg.update()
    else:
        await loader_msg.send()
        loader_state["sent"] = True

    loader_state["last_message"] = new_message