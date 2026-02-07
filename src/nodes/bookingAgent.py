import json
from typing import Literal
from langgraph.types import Command
from langchain_core.messages import SystemMessage, ToolMessage
from src.state.AgentState import AgentState
from src.models.model import get_llm, _rate_limit_wait
from src.prompts.bookingPrompts import get_system_prompt
from src.utils.common_tools import communicate_with_user
from src.utils.booking_tools import (
    get_bookings_by_user,
    get_all_bookings,
    prepare_booking_form,
    get_terminal_schedule,
)
from src.utils.terminal_tools import (
    get_bookings_by_terminal_id,
    get_capacity_by_terminal_id,
)
from src.utils.capacity_tools import get_terminals_map

# --- 2. THE NODE ---

def booking_agent_node(state: AgentState) -> Command[Literal["GUARDIAN"]]:
    print("📚 Booking Agent: Analyzing Request...")
    
    # A. Setup Context
    user_msg = state["messages"][-1].content
    user_id = state.get("user_id", "guest")
    user_role = state.get("user_role", "CARRIER") # Default to CARRIER
    
    tools_to_bind = []
    system_prompt = ""
    
    # B. BRANCHING LOGIC (The "Split Brain")

    if user_role == "ADMIN":
        print("   👤 Mode: ADMIN (full access)")

        # 1. Pre-fetch today's schedule + terminals map
        todays_data = get_terminal_schedule.invoke({"date": "TODAY"})
        terminals_map = get_terminals_map.invoke({})

        # 2. Admin gets ALL booking tools
        tools_to_bind = [
            get_all_bookings,
            get_bookings_by_terminal_id,
            get_capacity_by_terminal_id,
            get_terminal_schedule,
            communicate_with_user,
        ]

        # 3. Build admin prompt with full terminal map
        system_prompt = get_system_prompt(
            user_role, "", todays_data,
            operator_terminal_info="",
            terminals_map=terminals_map,
        )
    
    elif user_role == "OPERATOR":
        print("   👤 Mode: TERMINAL OPERATOR")
        
        # 1. Read terminal_id from state (resolved once at API level)
        terminal_id = state.get("terminal_id")
        operator_terminal_info = f"YOUR_TERMINAL_ID: {terminal_id}" if terminal_id else "No terminal assigned"
        print(f"   🏢 Operator terminal: {operator_terminal_info}")
        
        # 2. Pre-fetch today's schedule + terminals map (so operator can query other terminals too)
        todays_data = get_terminal_schedule.invoke({"date": "TODAY"})
        terminals_map = get_terminals_map.invoke({})
        
        # 3. Bind all operator tools
        tools_to_bind = [
            get_bookings_by_terminal_id,
            get_capacity_by_terminal_id,
            get_terminal_schedule,
            communicate_with_user,
        ]
        
        # 4. Build the operator prompt with terminal context + terminals map
        system_prompt = get_system_prompt(user_role, "", todays_data, operator_terminal_info, terminals_map)
        
    elif user_role == "CARRIER":
        print("   👤 Mode: CARRIER")
        
        # 1. Pre-fetch terminals map for terminal name matching
        terminals_map = get_terminals_map.invoke({})
        
        # 2. Carriers get the Booking Form Tool
        tools_to_bind = [prepare_booking_form, communicate_with_user, get_bookings_by_user]
        
        system_prompt = get_system_prompt(user_role, "", "", terminals_map=terminals_map)

    # C. EXECUTION
    llm = get_llm(model_type="medium")
    llm_with_tools = llm.bind_tools(tools_to_bind)
    
    _rate_limit_wait()
    response = llm_with_tools.invoke([SystemMessage(content=system_prompt)] + state["messages"])
    
    # D. HANDLE TOOLS (enforce single tool call)
    if response.tool_calls:
        # Take only the FIRST tool call to enforce one-tool-per-turn
        call = response.tool_calls[0]
        t_name = call["name"]
        ui_signal = None
        needs_followup = False

        print(f"   🔧 Executing tool: {t_name} with args: {call['args']}")

        # Execute the correct tool
        if t_name == "prepare_booking_form":
            result = prepare_booking_form.invoke(call["args"])
            parsed = json.loads(result)
            ui_signal = parsed  # Sent via ui_payload for the frontend
            # Build a simple human-readable confirmation text
            prefill = parsed.get("prefill", {})
            booking_text = f"I've prepared a booking form for you:\n• Date: {prefill.get('date', 'N/A')}\n• Time: {prefill.get('time', 'N/A')}\n• Terminal: {prefill.get('terminal', 'N/A')}\nPlease review and confirm in the form below."
        elif t_name == "get_terminal_schedule":
            result = get_terminal_schedule.invoke(call["args"])
        elif t_name == "communicate_with_user":
            result = communicate_with_user.invoke(call["args"])
            needs_followup = call["args"].get("needs_followup", False)
        elif t_name == "get_bookings_by_user":
            args = call["args"]
            args["user_id"] = state.get("user_id", "guest")
            args["user_role"] = state.get("user_role", "CARRIER")
            # Inject carrier_id so the backend filters correctly
            # (AI API authenticates as admin, so we must explicitly scope by carrier)
            carrier_id = state.get("carrier_id")
            if carrier_id:
                args["carrier_id"] = carrier_id
            print(f"   📋 Fetching bookings for user_id={args['user_id']} carrier_id={carrier_id} role={args['user_role']}")
            result = get_bookings_by_user.invoke(args)
        elif t_name == "get_bookings_by_terminal_id":
            result = get_bookings_by_terminal_id.invoke(call["args"])
        elif t_name == "get_capacity_by_terminal_id":
            result = get_capacity_by_terminal_id.invoke(call["args"])
        elif t_name == "get_all_bookings":
            result = get_all_bookings.invoke(call["args"])
        else:
            result = f"Unknown tool: {t_name}"

        tool_outputs = [ToolMessage(content=str(result), tool_call_id=call["id"], name=t_name)]
            
        # Optimization: If it was the UI signal, return immediately
        if ui_signal:
             return Command(
                update={
                    "messages": [response] + tool_outputs,
                    "draft_response": booking_text,
                    "ui_payload": ui_signal,
                    "route_lock": None
                },
                goto="GUARDIAN"
            )
        
        if needs_followup:
            return Command(
                update={
                    "messages": [response] + tool_outputs,
                    "draft_response": result["message"],
                    "route_lock": "BOOKING"
                },
                goto="GUARDIAN"
            )
        
        # Otherwise, let LLM summarize the tool result (e.g., for the Operator)
        _rate_limit_wait()
        final_response = llm_with_tools.invoke(
            [SystemMessage(content=system_prompt)] + state["messages"] + [response] + tool_outputs
        )
        
        return Command(
            update={
                "messages": [response] + tool_outputs + [final_response],
                "draft_response": final_response.content,
                "route_lock": None
            },
            goto="GUARDIAN"
        )
    # no tool calls, just a direct answer
    return Command(
        update={
            "messages": [response],
            "draft_response": response.content,
            "route_lock": None
        },
        goto="GUARDIAN"
    )    
