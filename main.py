import os
import uuid
from langchain_core.messages import HumanMessage, AIMessage
from src.graph.graph import build_agent_graph , get_checkpointer
from src.utils.auth_tools import login_and_store_tokens
from src.utils.token_store import clear_tokens
from src.utils.terminal_tools import resolve_terminal_id_for_user


def run_cli() -> None:
    # -------------------------------
    # Authentication bootstrap
    # -------------------------------
    admin_email = os.getenv("ADMIN_EMAIL", "admin@apcs-port.dz")
    admin_password = os.getenv("ADMIN_PASSWORD", "Admin@APCS2026!")

    # Authenticate on CLI start
    clear_tokens()
    ok = login_and_store_tokens(admin_email, admin_password)
    if not ok:
        print("⚠️  Warning: Login failed. Requests may be unauthorized.")

    # -------------------------------
    # CLI startup
    # -------------------------------
    print("🚢 Port Logistics Assistant (type 'exit' to quit)")

    user_id = "ee6e102e-d43a-42ac-ad38-a2d0941b3427"
    user_role = "ADMIN"

    existing_thread = input("Thread ID (leave blank for new): ").strip()
    thread_id = existing_thread or str(uuid.uuid4())

    if existing_thread:
        print(f"🔁 Resuming thread: {thread_id}")
    else:
        print(f"🆕 Starting new thread: {thread_id}")

    # -------------------------------
    # Resolve operator terminal once
    # -------------------------------
    terminal_id = None
    if user_role == "OPERATOR" and user_id:
        terminal_id = resolve_terminal_id_for_user(user_id)
        print(f"🏢 Operator terminal_id: {terminal_id}")

    # -------------------------------
    # Build & compile graph ONCE
    # -------------------------------
    print("⚙️  Building agent graph...")
    graph = build_agent_graph(get_checkpointer())
    print("✅ Graph built successfully. You can start chatting now!")
    # -------------------------------
    # Conversation loop
    # -------------------------------
    while True:
        user_text = input("\nYou: ").strip()

        if not user_text:
            continue

        if user_text.lower() in {"exit", "quit"}:
            print("👋 Goodbye.")
            break

        # Invoke graph with ONLY the new message
        result = graph.invoke(
            {
                "messages": [HumanMessage(content=user_text)],
                "user_id": user_id,
                "user_role": user_role,
                "thread_id": thread_id,
                "terminal_id": terminal_id,
            },
            config={
                "configurable": {
                    "thread_id": thread_id
                }
            },
        )

        # Print assistant response
        if result.get("messages"):
            last_msg = result["messages"][-1]
            if isinstance(last_msg, AIMessage):
                print(f"Assistant: {last_msg.content}")

        # Optional UI payload (forms, actions, etc.)
        if result.get("ui_payload"):
            print(f"[UI] {result['ui_payload']}")


if __name__ == "__main__":
    run_cli()
