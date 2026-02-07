"""
Suggestion service — fetches capacity data for the current week
and uses the LLM to generate short actionable admin suggestions.
Completely standalone, not part of the AI chatbot graph.
"""
import datetime
from src.utils.api_client import api_get
from src.models.model import get_llm, _rate_limit_wait


def _week_range() -> tuple[str, str]:
    """Return (start_date, end_date) for the current week (Mon–Sun)."""
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def _fetch_overview() -> dict:
    """GET /api/analytics/overview — system-wide stats."""
    try:
        resp = api_get("/api/analytics/overview")
        return resp.json().get("overview", {})
    except Exception as exc:
        print(f"[suggestions] overview fetch failed: {exc}")
        return {}


def _fetch_utilization(start: str, end: str) -> list:
    """GET /api/analytics/capacity/utilization — per-terminal utilization for date range."""
    try:
        resp = api_get(
            "/api/analytics/capacity/utilization",
            params={"startDate": start, "endDate": end},
        )
        return resp.json().get("utilization", [])
    except Exception as exc:
        print(f"[suggestions] utilization fetch failed: {exc}")
        return []


def _fetch_day_summary(date: str) -> list:
    """GET /api/analytics/terminals/all/day-summary — slot-level summary for all terminals."""
    try:
        resp = api_get(
            "/api/analytics/terminals/all/day-summary",
            params={"date": date},
        )
        return resp.json().get("summaries", [])
    except Exception as exc:
        print(f"[suggestions] day-summary fetch failed: {exc}")
        return []


def _build_data_snapshot() -> str:
    """Gather all relevant data and format it as a text block for the LLM."""
    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    start, end = _week_range()

    overview = _fetch_overview()
    utilization = _fetch_utilization(start, end)

    # Fetch day-summary for every day of the week
    monday = today - datetime.timedelta(days=today.weekday())
    week_days = [(monday + datetime.timedelta(days=i)) for i in range(7)]

    parts = [f"=== SYSTEM OVERVIEW (as of {today_str}) ==="]
    if overview:
        for k, v in overview.items():
            parts.append(f"  {k}: {v}")
    else:
        parts.append("  No overview data available.")

    parts.append(f"\n=== CAPACITY UTILIZATION THIS WEEK ({start} → {end}) ===")
    if utilization:
        for item in utilization:
            name = item.get("name", item.get("key", "?"))
            rate = item.get("utilizationRate", 0)
            booked = item.get("bookedCapacity", 0)
            total = item.get("totalCapacity", 0)
            slots = item.get("slotsCount", 0)
            parts.append(
                f"  {name}: {rate}% utilization | booked {booked}/{total} | {slots} slots"
            )
    else:
        parts.append("  No utilization data available.")

    parts.append(f"\n=== DAILY SLOT BREAKDOWN (week of {start} → {end}) ===")
    for day in week_days:
        day_str = day.strftime("%Y-%m-%d")
        day_label = "TODAY" if day == today else day.strftime("%A")
        summaries = _fetch_day_summary(day_str)

        parts.append(f"\n  [{day_str} — {day_label}]")
        if summaries:
            for summary in summaries:
                terminal = summary.get("terminal", {})
                code = terminal.get("code") or terminal.get("name") or "?"
                slots = summary.get("slots", [])
                total_slots = len(slots)
                full_count = sum(1 for s in slots if not s.get("isAvailable", True) or s.get("available", 0) <= 0)
                total_booked = sum(s.get("booked", 0) for s in slots)
                total_capacity = sum(s.get("capacity", 0) for s in slots)
                day_rate = round((total_booked / total_capacity * 100), 1) if total_capacity > 0 else 0
                parts.append(
                    f"    Terminal {code}: {full_count}/{total_slots} slots FULL | booked {total_booked}/{total_capacity} ({day_rate}%)"
                )
        else:
            parts.append(f"    No data available.")

    return "\n".join(parts)


SUGGESTION_PROMPT = """You are a port logistics advisor for a terminal management system administrator.

You are given a FULL WEEK of capacity data (day-by-day slot breakdowns, overall utilization, and system overview).
Analyze trends across the entire week before making suggestions.

Generate 3-6 actionable suggestions for the admin.

Focus on:
- Terminals with consistently HIGH utilization (>85%) across multiple days: suggest increasing capacity
- Terminals with consistently LOW utilization (<30%) across multiple days: suggest reducing capacity or closing
- Day-of-week patterns (weekends empty, mid-week full): suggest adjusting capacity per day
- If ALL terminals are overloaded most days: suggest adding a new terminal
- If a terminal has 0% or no bookings most of the week: suggest closing or investigating
- Imbalances between terminals (one overloaded, another empty on same days)
- Sudden spikes or drops on specific days

Return ONLY a valid JSON array. Each element must have these keys:
  "priority": one of "high", "medium", or "low"
  "category": a short label like "Increase Capacity", "Reduce Capacity", "Add Terminal", "Close Terminal", "Rebalance", "Day Pattern", "Investigate"
  "terminal": the terminal name/code this applies to, or "All Terminals" / "System-wide" if general
  "suggestion": a clear 1-2 sentence actionable recommendation mentioning specific numbers and days

Example output:
[
  {{"priority": "high", "category": "Increase Capacity", "terminal": "Terminal A", "suggestion": "Terminal A exceeded 90% utilization on Monday-Wednesday. Consider adding 2 extra slots or extending hours on weekdays."}},
  {{"priority": "low", "category": "Reduce Capacity", "terminal": "Terminal C", "suggestion": "Terminal C averaged only 12% utilization all week. Consider temporarily closing it and redirecting traffic to Terminal B."}}
]

Do NOT include any text outside the JSON array. No markdown, no explanation.

DATA:
{data}

JSON:"""


import json as _json
import re as _re

PRIORITY_ICONS = {"high": "🔴", "medium": "🟡", "low": "🟢"}


def _parse_suggestions(raw: str) -> list[dict]:
    """Try to extract a JSON array from the LLM response, with fallbacks."""
    # Strip markdown code fences if present
    cleaned = _re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
    try:
        parsed = _json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
    except _json.JSONDecodeError:
        pass
    # Fallback: return raw text as a single suggestion
    return [{"priority": "medium", "category": "General", "terminal": "—", "suggestion": raw.strip()}]


def generate_suggestions() -> dict:
    """
    Main entry point: fetch data, call LLM, return structured suggestions.
    Returns {
        "suggestions": [  {priority, icon, category, terminal, suggestion}, ... ],
        "generated_at": str
    }
    """
    print("[suggestions] Fetching capacity data...")
    data_snapshot = _build_data_snapshot()
    print(f"[suggestions] Data snapshot:\n{data_snapshot[:300]}...")

    prompt = SUGGESTION_PROMPT.format(data=data_snapshot)

    llm = get_llm(model_type="small", temperature=0.3)
    _rate_limit_wait()

    print("[suggestions] Calling LLM for suggestions...")
    response = llm.invoke(prompt)
    raw_items = _parse_suggestions(response.content)

    # Normalize and enrich each suggestion
    suggestions = []
    for item in raw_items:
        priority = item.get("priority", "medium").lower()
        suggestions.append({
            "priority": priority,
            "icon": PRIORITY_ICONS.get(priority, "🟡"),
            "category": item.get("category", "General"),
            "terminal": item.get("terminal", "—"),
            "suggestion": item.get("suggestion", ""),
        })

    # Sort: high first, then medium, then low
    order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda s: order.get(s["priority"], 1))

    return {
        "suggestions": suggestions,
        "generated_at": datetime.datetime.now().isoformat(),
    }
