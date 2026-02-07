"""Shared tools used by multiple agents."""
from typing import List, Optional
from langchain_core.tools import tool


@tool
def communicate_with_user(
    message: str,
    needs_followup: bool,
    missing_fields: Optional[List[str]] = None
):
    """
    Use this tool to send a message to the user when you need clarification
    or want to ask a follow-up question.

    Args:
        message: The message text to show the user.
        needs_followup: True if you need the user to respond before continuing.
        missing_fields: List of field names still needed (e.g. ["date", "terminal"]).
    """
    return {
        "type": "communication",
        "message": message,
        "needs_followup": needs_followup,
        "missing_fields": missing_fields or []
    }
