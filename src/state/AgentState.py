from typing import Any, Literal, TypedDict, Annotated, List, Union, Dict, Optional
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """
    Represents the memory of the agent workflow.
    """
    
    # --- CONVERSATION HISTORY ---
    # We use 'add_messages' so that when a node returns {"messages": [new_msg]},
    # it APPENDS to this list rather than deleting the old history.
    messages: Annotated[List[AnyMessage], add_messages]

    current_intent: Union[str, None]  # e.g., "booking", "capacity", "history", "chitchat"
    language_detected: Union[str, None]  # e.g., "en", "es", "fr"
    draft_response: Union[str, None]  # For Guardian to fill in and return to user
    
    # Clarification handling
    route_lock: Union[str, None]  # To lock routing to a specific agent
    
    # Multi-intent handling
    pending_intents: List[str]  # Queue of intents still to be processed (e.g., ["BOOKING"] after CAPACITY is done)
    
    user_id: Union[str, None]  # To track user-specific data (e.g., bookings)
    user_role: Literal["CARRIER", "OPERATOR", "ADMIN"]
    terminal_id: Union[str, None]  # To scope data access (OPERATOR)
    carrier_id: Union[str, None]  # To scope data access (CARRIER)
    thread_id: Union[str, None]  # To group related interactions
    
    # UI payload — None by default, only set when prepare_booking_form tool is used
    ui_payload: Optional[Dict[str, Any]]  # None = no form, non-null = booking form data for frontend
