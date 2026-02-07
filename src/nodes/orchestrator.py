import json
from typing import Literal
from langgraph.types import Command
from langchain_core.messages import SystemMessage, HumanMessage
from src.state.AgentState import AgentState
from src.models.model import get_llm, _rate_limit_wait
from src.prompts.orchestratorPrompts import get_system_prompt


def classify_intent_and_language(user_msg: str, history_str: str, active_route: str, previous_intent: str) -> dict:
    """
    Uses the medium LLM to classify intent AND detect language in a single call.
    Returns {"intent": "BOOKING", "language": "English"}
    """
    llm = get_llm(model_type="medium")
    
    system_prompt = get_system_prompt(history_str, active_route, previous_intent)
    
    _rate_limit_wait()
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_msg)
    ])
    
    raw = response.content.strip()
    
    # Parse the JSON response
    try:
        parsed = json.loads(raw)
        result = {
            "intent": parsed.get("intent", "CHITCHAT").strip().upper(),
            "language": parsed.get("language", "English").strip()
        }
        # Preserve multi-intent list if present
        if "intents" in parsed:
            result["intents"] = parsed["intents"]
        return result
    except json.JSONDecodeError:
        # Fallback: treat the whole response as an intent (backward compat)
        return {
            "intent": raw.upper(),
            "language": "English"
        }

def orchestrator_node(state: AgentState) -> Command[Literal["BOOKING", "CAPACITY", "GUARDIAN"]]:
    """
    1. Analyzes the user's input to determine Intent.
    2. Routes to the specific specialist agent.
    3. Handles 'chitchat' by routing directly to Guardian with a pre-filled draft.
    4. If returning from clarification, routes back to the previous agent.
    """
    print("🧠 Orchestrator: Analyzing user intent...")
    
    active_route = state.get("route_lock", "NONE")
    previous_intent = state.get("current_intent", "NONE") or "NONE"
    
    # 1. Get the latest user message + recent history
    recent_messages = state["messages"][-5:] 
    history_str = "\n".join([f"{m.type.upper()}: {m.content}" for m in recent_messages])
    user_msg = state["messages"][-1].content
    
    # 2. Classify intent AND detect language in one LLM call
    classification = classify_intent_and_language(user_msg, history_str, active_route, previous_intent)
    
    intent = classification["intent"]
    language = classification["language"]
    print(f"👉 Intent Detected: {intent} | Language: {language}")

    # 3. Check if returning from a completed sub-intent (multi-intent continuation)
    valid_nodes = {"BOOKING", "CAPACITY"}
    pending = state.get("pending_intents", []) or []
    if pending and intent not in ("MULTI", "BOOKING", "CAPACITY", "CHITCHAT"):
        # Orchestrator was re-entered after Guardian; pop next pending intent
        next_intent = pending[0]
        remaining = pending[1:]
        if next_intent in valid_nodes:
            print(f"🔄 Multi-intent continuation: processing {next_intent} (remaining: {remaining})")
            return Command(
                update={
                    "current_intent": next_intent.lower(),
                    "language_detected": language,
                    "pending_intents": remaining,
                },
                goto=next_intent
            )
        else:
            print(f"⚠️ Skipping invalid pending intent: {next_intent}")

    # 4. Routing Logic

    # CASE 0: MULTI — compound request with multiple intents
    if "MULTI" in intent:
        intents_list = classification.get("intents", ["CAPACITY", "BOOKING"])
        # Normalize
        intents_list = [i.strip().upper() for i in intents_list if i.strip().upper() in ("BOOKING", "CAPACITY")]
        if len(intents_list) < 2:
            intents_list = ["CAPACITY", "BOOKING"]  # Safe fallback
        
        first_intent = intents_list[0]
        remaining_intents = intents_list[1:]
        print(f"🔀 Multi-intent detected: {intents_list} → starting with {first_intent}, queuing {remaining_intents}")
        
        return Command(
            update={
                "current_intent": first_intent.lower(),
                "language_detected": language,
                "pending_intents": remaining_intents,
            },
            goto=first_intent
        )
    
    # CASE A: Booking Questions -> Booking Agent
    if "BOOKING" in intent:
        return Command(
            update={"current_intent": "booking", "language_detected": language, "pending_intents": []},
            goto="BOOKING"
        )
        
    # CASE B: Capacity/Slot Questions -> Capacity Agent
    elif "CAPACITY" in intent:
        return Command(
            update={"current_intent": "capacity", "language_detected": language, "pending_intents": []},
            goto="CAPACITY"
        )

    # # CASE C: History/Logs -> History Agent
    # elif "HISTORY" in intent:
    #     return Command(
    #         update={"current_intent": "history", "language_detected": language},
    #         goto="HISTORY"
    #     )
        
    # CASE D: HELP — user asks what the assistant can do
    elif "HELP" in intent:
        user_role = state.get("user_role", "CARRIER")
        help_lines = [
            "I'm the **Port Logistics Assistant**. Here's what I can help you with:",
            "",
        ]
        if user_role == "ADMIN":
            help_lines += [
                "- **Bookings** — View all bookings across every terminal, search by carrier, status, or terminal, and manage booking operations.",
                "- **Capacity** — Check real-time capacity, slot availability, and utilization for any terminal on any date.",
                "- **Terminals** — Get an overview of all terminals in the system.",
            ]
        elif user_role == "OPERATOR":
            help_lines += [
                "- **Bookings** — View and manage bookings for your terminal.",
                "- **Capacity** — Check slot availability and capacity status for your terminal on any date.",
            ]
        else:  # CARRIER
            help_lines += [
                "- **Bookings** — View your bookings, check booking status, or start a new booking.",
                "- **Capacity** — Check available time slots and terminal capacity for any date.",
            ]
        help_lines += [
            "",
            "Just ask me a question and I'll take care of the rest!",
        ]
        help_text = "\n".join(help_lines)
        print(f"   Routing to Guardian (HELP) — role={user_role}")
        return Command(
            update={
                "draft_response": help_text,
                "current_intent": "general",
                "language_detected": language,
                "pending_intents": [],
            },
            goto="GUARDIAN"
        )

    # CASE E: OUT_OF_SCOPE — unrelated question
    elif "OUT_OF_SCOPE" in intent:
        print("   Routing to Guardian (OUT_OF_SCOPE).")
        return Command(
            update={
                "draft_response": "I'm sorry, I can only help with port logistics — bookings, terminal capacity, and scheduling. I can't assist with that topic. Is there anything else I can help you with?",
                "current_intent": "general",
                "language_detected": language,
                "pending_intents": [],
            },
            goto="GUARDIAN"
        )

    # CASE F: Greetings/Chitchat -> Skip Workers, Go to Guardian
    else:
        print("   Direct routing to Guardian (Chitchat).")
        return Command(
            update={
                "draft_response": "Hello! I'm the Port Logistics Assistant. I can help you with bookings, terminal capacity, and scheduling. What would you like to know?",
                "current_intent": "general",
                "language_detected": language,
                "pending_intents": [],
            },
            goto="GUARDIAN"
        )