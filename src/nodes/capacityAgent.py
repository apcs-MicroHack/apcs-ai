from typing import Literal
from langgraph.types import Command
from langchain_core.messages import SystemMessage, ToolMessage
from src.models.model import get_llm, _rate_limit_wait
from src.prompts.capacityPrompts import get_system_prompt
from src.utils.common_tools import communicate_with_user
from src.utils.capacity_tools import (
    get_capacity_summary,
    get_terminals_map,
    get_terminal_details,
)
from src.utils.booking_tools import check_availability
from src.utils.terminal_tools import (
    get_capacity_by_terminal_id,
)

# --- 3. THE NODE LOGIC ---
def capacity_node(state) -> Command[Literal["GUARDIAN"]]:
    print("🏗️ Capacity Agent: Scanning Dashboard...")
    
    user_role = state.get("user_role", "CARRIER")
    user_id = state.get("user_id", "guest")
    
    terminals_map = get_terminals_map.invoke({})

    # B. Setup LLM & Tools — add operator-specific tools when applicable
    llm = get_llm(model_type="medium")
    
    base_tools = [check_availability, get_terminal_details, communicate_with_user, get_capacity_summary]
    
    operator_terminal_info = ""
    if user_role == "ADMIN":
        print("   👤 Mode: ADMIN (full capacity access)")
        base_tools.append(get_capacity_by_terminal_id)
    elif user_role == "OPERATOR":
        terminal_id = state.get("terminal_id")
        operator_terminal_info = f"Terminal ID: {terminal_id}" if terminal_id else "No terminal assigned"
        print(f"   🏢 Operator terminal: {operator_terminal_info}")
        base_tools.append(get_capacity_by_terminal_id)
    
    llm_with_tools = llm.bind_tools(base_tools)
    print(f"   📋 Available terminals: {list(terminals_map.keys())}")

    system_msg = get_system_prompt(terminals_map, user_role=user_role, operator_terminal_info=operator_terminal_info)
    
    # C. First LLM Call (Think & Decide)
    messages = state["messages"]
    _rate_limit_wait()
    ai_msg = llm_with_tools.invoke([SystemMessage(content=system_msg)] + messages)
    
    # D. Tool Execution Loop (enforce single tool call)
    if ai_msg.tool_calls:
        call = ai_msg.tool_calls[0]
        t_name = call["name"]
        print(f"   🔧 Executing tool: {t_name} with args: {call['args']}")

        needs_followup = False

        if t_name == "get_terminal_details":
            result = get_terminal_details.invoke(call["args"])
        elif t_name == "get_capacity_summary":
            result = get_capacity_summary.invoke(call["args"])
        elif t_name == "communicate_with_user":
            result = communicate_with_user.invoke(call["args"])
            needs_followup = call["args"].get("needs_followup", False)
        elif t_name == "check_availability":
            result = check_availability.invoke(call["args"])
        elif t_name == "get_capacity_by_terminal_id":
            result = get_capacity_by_terminal_id.invoke(call["args"])
        else:
            result = f"Unknown tool: {t_name}"

        tool_outputs = [ToolMessage(
            content=str(result),
            tool_call_id=call["id"],
            name=t_name
        )]

        # If agent needs clarification from user, skip second LLM call
        if needs_followup:
            return Command(
                update={
                    "messages": [ai_msg] + tool_outputs,
                    "draft_response": result["message"],
                    "route_lock": "CAPACITY"
                },
                goto="GUARDIAN"
            )
        
        # E. Second LLM Call (Synthesize with Deep Data)
        _rate_limit_wait()
        final_response = llm_with_tools.invoke(
             [SystemMessage(content=system_msg)] + messages + [ai_msg] + tool_outputs
        )
        
        return Command(
            update={
                "messages": [ai_msg] + tool_outputs + [final_response],
                "draft_response": final_response.content,
                "route_lock": None
            },
            goto="GUARDIAN"
        )

    # Fallback (User just asked for general status, no tool needed)
    return Command(
        update={
            "messages": [ai_msg],
            "draft_response": ai_msg.content,
            "route_lock": None
        },
        goto="GUARDIAN"
    )