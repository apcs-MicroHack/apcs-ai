from typing import Literal
from langgraph.types import Command
from langchain_core.messages import SystemMessage, AIMessage
from src.state.AgentState import AgentState
from src.models.model import get_llm, _rate_limit_wait
from src.prompts.guardianPrompts import get_system_prompt, get_system_prompt_form_generation


# --- 1. PERMISSION RULES ---

ROLE_PERMISSIONS = {
    "CARRIER": {
        "allowed_intents": ["booking", "capacity", "general"],
        "can_view_capacity": True,
        "can_view_history": True,
        "label": "Truck Carrier"
    },
    "OPERATOR": {
        "allowed_intents": ["booking", "capacity", "general"],
        "can_view_capacity": True,
        "can_view_history": True,
        "label": "Terminal Operator"
    },
    "ADMIN": {
        "allowed_intents": ["booking", "capacity", "general"],
        "can_view_capacity": True,
        "can_view_history": True,
        "label": "Port Administrator"
    }
}


def check_permission(user_role: str, intent: str) -> bool:
    """Check if a role is allowed to access data for this intent."""
    role_config = ROLE_PERMISSIONS.get(user_role, ROLE_PERMISSIONS["CARRIER"])
    return intent in role_config["allowed_intents"]


# --- 2. THE NODE ---

def guardian_node(state: AgentState) -> Command[Literal["__end__", "BOOKING", "CAPACITY"]]:
    """
    The Guardian is the FINAL node before responding to the user.
    
    Responsibilities:
    1. Permission Check: Block unauthorized data access.
    2. Response Polishing: Format the draft_response into a branded, clean answer.
    3. Language Adaptation: Respond in the user's detected language.
    4. Safety Filter: Strip sensitive data or hallucinated content.
    5. Logging: Record the final response for audit trail.
    """
    print("🛡️  Guardian: Final review before responding...")
    
    # A. GATHER CONTEXT
    draft = state.get("draft_response", None)
    intent = state.get("current_intent", "general")
    language = state.get("language_detected", "English")
    user_role = state.get("user_role", "CARRIER")
    ui_payload = state.get("ui_payload", None)
    
    # B. PERMISSION CHECK
    if not check_permission(user_role, intent):
        role_label = ROLE_PERMISSIONS.get(user_role, {}).get("label", "User")
        blocked_msg = f"Access Denied: As a {role_label}, you do not have permission to access {intent} data. Please contact your terminal operator for assistance."
        
        print(f"   🚫 Permission blocked: {user_role} cannot access '{intent}'")
        
        return Command(
            update={
                "messages": [AIMessage(content=blocked_msg)],
                "draft_response": None,
                "ui_payload": None
            },
            goto="__end__"
        )
    
    # C. HANDLE EMPTY DRAFT (Fallback)
    if not draft:
        print("   ⚠️  No draft response received. Generating fallback.")
        draft = "I'm sorry, I couldn't process your request. Could you rephrase that?"
    
    # D. POLISH & FORMAT RESPONSE
    llm = get_llm(model_type="medium")
    
    if ui_payload:
        system_prompt = get_system_prompt_form_generation(draft, language, user_role, intent, ui_payload)
    else:
        system_prompt = get_system_prompt(draft, language, user_role, intent)
    
    _rate_limit_wait()
    result = llm.invoke([SystemMessage(content=system_prompt)])
    final_content = result.content.strip()
    
    print(f"   ✅ Guardian approved response ({len(final_content)} chars)")
    
    # E. BUILD FINAL STATE UPDATE
    # route_lock is set by agents: "BOOKING"/"CAPACITY" for followup, None otherwise
    route_lock = state.get("route_lock", None)
    
    update = {
        "messages": [AIMessage(content=final_content)],
        "draft_response": None,
        "route_lock": route_lock,
        # Always explicitly set ui_payload: non-null only when booking form was triggered
        "ui_payload": ui_payload if ui_payload else None,
    }
    
    # F. AUDIT LOG (placeholder - connect to DB/logging in production)
    print(f"   📋 Audit: intent={intent}, role={user_role}, response_length={len(final_content)}")
    
    # G. CHECK FOR PENDING INTENTS (multi-intent continuation)
    pending = state.get("pending_intents", []) or []
    valid_targets = {"BOOKING", "CAPACITY"}
    if pending and not route_lock:
        next_intent = pending[0]
        remaining = pending[1:]
        if next_intent in valid_targets:
            print(f"   🔄 Pending intents remaining: {pending} → routing to {next_intent}")
            update["pending_intents"] = remaining
            update["current_intent"] = next_intent.lower()
            return Command(
                update=update,
                goto=next_intent
            )
        else:
            print(f"   ⚠️ Skipping invalid pending intent: {next_intent}")
            update["pending_intents"] = remaining
    
    return Command(
        update=update,
        goto="__end__"
    )
