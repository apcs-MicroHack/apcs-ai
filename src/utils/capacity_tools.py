"""Capacity / terminal analytics tools."""
import datetime
from typing import Dict
from langchain_core.tools import tool
from src.utils.api_client import api_get


@tool
def get_terminals_map() -> Dict[str, str]:
    """
    Fetch terminals and return a mapping of terminal name -> terminal UUID.
    """
    try:
        resp = api_get("/api/terminals")
        data = resp.json()
    except Exception as exc:
        print(f"get_terminals_map failed: {exc}")
        return {}

    terminals = data.get("terminals", []) if isinstance(data, dict) else []
    return {
        str(t.get("name") or t.get("code")): str(t["id"])
        for t in terminals
        if t.get("id") and (t.get("name") or t.get("code"))
    }


@tool
def get_capacity_summary(
    date: str = "TODAY",
    terminal_id: str = "ALL",
):
    """Fetch the capacity / schedule summary for one or all terminals on a given date.
    Use this for general overview, specific terminal details, or schedule checks.

    Args:
        date: Date in YYYY-MM-DD format, or "TODAY" / "TOMORROW".
        terminal_id: Terminal UUID, or "ALL" for every terminal.
    """
    date = _resolve_date(date)
    terminal_path = terminal_id if terminal_id and terminal_id != "ALL" else "all"

    try:
        resp = api_get(
            f"/api/analytics/terminals/{terminal_path}/day-summary",
            params={"date": date},
        )
        data = resp.json()
    except Exception as exc:
        print(f"get_capacity_summary failed: {exc}")
        return f"--- SCHEDULE REPORT FOR {date} (Terminal {terminal_id}) ---\nNo data available."

    summaries = data.get("summaries", [])
    if not isinstance(summaries, list) or not summaries:
        return f"--- SCHEDULE REPORT FOR {date} ---\nNo data available."

    output = [f"--- SCHEDULE REPORT FOR {date} ---"]
    for summary in summaries:
        terminal = summary.get("terminal", {})
        terminal_code = terminal.get("code") or terminal.get("name") or "UNKNOWN"
        output.append(f"\nTerminal {terminal_code}:")

        slots = summary.get("slots", [])
        if not isinstance(slots, list) or not slots:
            output.append("  No slots available.")
            continue

        for slot in slots:
            s = slot.get("startTime", "")
            e = slot.get("endTime", "")
            booked = slot.get("booked", 0)
            capacity = slot.get("capacity", 0)
            available = slot.get("available", 0)
            status = "FULL" if (not slot.get("isAvailable", True) or available <= 0) else "AVAILABLE"
            output.append(f"  {s} - {e} | booked: {booked} | available: {available} | max: {capacity} | status: {status}")

    return "\n".join(output)


@tool
def get_terminal_details(
    date: str = "TODAY",
    terminal_id: str = "ALL",
):
    """Fetch detailed slot-level data for a specific terminal on a given date.
    Prefer this when the user asks about a single terminal in depth.

    Args:
        date: Date in YYYY-MM-DD format, or "TODAY" / "TOMORROW".
        terminal_id: Terminal UUID (required for meaningful results).
    """
    # Delegate to the same underlying logic
    return get_capacity_summary.invoke({"date": date, "terminal_id": terminal_id})


def _resolve_date(value: str) -> str:
    """Convert relative date strings to YYYY-MM-DD."""
    v = (value or "").strip().upper()
    today = datetime.date.today()
    if v in ("TODAY", ""):
        return today.strftime("%Y-%m-%d")
    if v == "TOMORROW":
        return (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    if v == "YESTERDAY":
        return (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    return value
