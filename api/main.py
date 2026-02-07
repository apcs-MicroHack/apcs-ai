import os
import sys
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.graph.graph import build_agent_graph , get_checkpointer
from src.utils.auth_tools import login_and_store_tokens
from src.utils.token_store import clear_tokens
from src.utils.terminal_tools import resolve_terminal_id_for_user, resolve_carrier_id_for_user
from src.services.suggestion_service import generate_suggestions


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Authenticate on startup
    admin_email = os.getenv("ADMIN_EMAIL", "admin@apcs.dz")
    admin_password = os.getenv("ADMIN_PASSWORD", "adminadmin2026")
    api_base = os.getenv("API_BASE_URL", "NOT SET")
    print(f"[API Lifespan] email={admin_email}, API_BASE_URL={api_base}")
    clear_tokens()
    ok = login_and_store_tokens(admin_email, admin_password)
    if not ok:
        print("Warning: Login failed. Requests may be unauthorized.")

    app.state.graph = build_agent_graph(get_checkpointer())
    yield


app = FastAPI(title="Microhack Agentic AI API", lifespan=lifespan)


def _require_api_key(x_api_key: Optional[str]) -> None:
    expected = os.getenv("AGENT_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="AGENT_API_KEY is not configured")
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


class ChatRequest(BaseModel):
    message: str = Field(..., description="User input message")
    user_id: Optional[str] = Field(default="guest", description="User ID for agent state")
    user_role: Optional[str] = Field(default="CARRIER", description="CARRIER | OPERATOR | ADMIN")
    thread_id: Optional[str] = Field(default=None, description="Conversation thread id")


class ResponseBlock(BaseModel):
    type: str = Field(..., description="Block type: always 'message' for markdown content")
    text: Optional[str] = Field(default=None, description="Markdown text content")


class ChatResponse(BaseModel):
    message: str = Field(..., description="Raw message content (JSON string of blocks)")
    blocks: list[ResponseBlock] = Field(default=[], description="Structured response blocks for frontend rendering")
    thread_id: str
    ui_payload: Optional[Dict[str, Any]] = None
    route_lock: Optional[str] = None
    current_intent: Optional[str] = None
    language_detected: Optional[str] = None


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, x_api_key: Optional[str] = Header(default=None)) -> ChatResponse:
    _require_api_key(x_api_key)

    thread_id = req.thread_id or str(uuid.uuid4())

    # Resolve operator terminal_id once (None for non-operators)
    terminal_id = None
    carrier_id = None
    if (req.user_role or "").upper() == "OPERATOR" and req.user_id:
        terminal_id = resolve_terminal_id_for_user(req.user_id)
    elif (req.user_role or "").upper() == "CARRIER" and req.user_id:
        carrier_id = resolve_carrier_id_for_user(req.user_id)

    input_state = {
        "messages": [HumanMessage(content=req.message)],
        "user_id": req.user_id or "guest",
        "user_role": req.user_role or "CARRIER",
        "thread_id": thread_id,
        "terminal_id": terminal_id,
        "carrier_id": carrier_id,
    }

    result = app.state.graph.invoke(input_state, config={"configurable": {"thread_id": thread_id}})

    assistant_message = ""
    blocks = []
    if result.get("messages"):
        last_msg = result["messages"][-1]
        if isinstance(last_msg, AIMessage):
            assistant_message = last_msg.content
        else:
            assistant_message = str(last_msg)

        # Wrap markdown response as a single message block
        blocks = [{"type": "message", "text": assistant_message}]

    return ChatResponse(
        message=assistant_message,
        blocks=blocks,
        thread_id=thread_id,
        ui_payload=result.get("ui_payload"),
        route_lock=result.get("route_lock"),
        current_intent=result.get("current_intent"),
        language_detected=result.get("language_detected"),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Suggestions endpoint (standalone, not part of the chatbot)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SuggestionItem(BaseModel):
    priority: str = Field(..., description="Priority level: high, medium, or low")
    icon: str = Field(..., description="Emoji icon for priority (🔴 high, 🟡 medium, 🟢 low)")
    category: str = Field(..., description="Short action label (e.g. Increase Capacity, Close Terminal)")
    terminal: str = Field(..., description="Terminal name this applies to, or System-wide")
    suggestion: str = Field(..., description="Actionable recommendation text")


class SuggestionResponse(BaseModel):
    suggestions: List[SuggestionItem] = Field(..., description="AI-generated admin suggestions")
    generated_at: str = Field(..., description="ISO timestamp of generation")


@app.get("/suggestions", response_model=SuggestionResponse)
def get_suggestions(x_api_key: Optional[str] = Header(default=None)) -> SuggestionResponse:
    """
    Fetch this week's capacity data and return AI-generated suggestions
    for the admin (e.g. increase/decrease capacity, add/close terminals).
    """
    _require_api_key(x_api_key)

    try:
        result = generate_suggestions()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate suggestions: {exc}")

    return SuggestionResponse(
        suggestions=result["suggestions"],
        generated_at=result["generated_at"],
    )
