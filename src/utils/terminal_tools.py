"""Terminal operator tools — resolve operator terminal, bookings, and capacity."""
import datetime
from typing import Optional
from langchain_core.tools import tool
from src.utils.api_client import api_get


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Resolve operator → terminal (plain function, called once at API/CLI level)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def resolve_terminal_id_for_user(user_id: str) -> str | None:
    """
    Calls GET /api/users/:id (admin-only endpoint).
    Extracts the operator's assigned terminal UUID from the response:
      response.user.operatorTerminal.terminal.id
    Returns the terminal UUID string or None.
    """
    try:
        resp = api_get(f"/api/users/{user_id}")
        data = resp.json()
    except Exception as exc:
        print(f"resolve_terminal_id_for_user failed: {exc}")
        return None

    user = data.get("user", {})
    # getUserById returns: user.operatorTerminal.terminal.{id, name, code, type, isActive}
    op_terminal = user.get("operatorTerminal", {}) or {}
    terminal = op_terminal.get("terminal", {}) or {}

    return terminal.get("id")


def resolve_carrier_id_for_user(user_id: str) -> str | None:
    """
    Calls GET /api/users/:id (admin-only endpoint).
    Extracts the carrier UUID from the response:
      response.user.carrier.id
    Returns the carrier UUID string or None.
    """
    try:
        resp = api_get(f"/api/users/{user_id}")
        data = resp.json()
    except Exception as exc:
        print(f"resolve_carrier_id_for_user failed: {exc}")
        return None

    user = data.get("user", {})
    carrier = user.get("carrier", {}) or {}
    carrier_id = carrier.get("id")
    print(f"   📋 Resolved carrier_id={carrier_id} for user_id={user_id}")
    return carrier_id


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Bookings by terminal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@tool
def get_bookings_by_terminal_id(
    terminal_id: str,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    Fetch bookings for a specific terminal via GET /api/bookings?terminalId=...
    The operator's terminal_id is already resolved and stored in state.

    Args:
        terminal_id: Terminal UUID (from operator's state).
        status: Filter by status — PENDING, CONFIRMED, CONSUMED, CANCELLED, REJECTED (UPPERCASE).
        start_date: Filter from date (YYYY-MM-DD). Defaults to today.
        end_date: Filter to date (YYYY-MM-DD). Defaults to today + 7 days.
    """
    today = datetime.date.today()
    start_date = _resolve_date(start_date) if start_date else today.strftime("%Y-%m-%d")
    end_date = _resolve_date(end_date) if end_date else (today + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    normalized_status = status.upper().strip() if status else None

    params = {
        "terminalId": terminal_id,
        "startDate": start_date,
        "endDate": end_date,
    }
    if normalized_status:
        params["status"] = normalized_status

    try:
        resp = api_get("/api/bookings", params=params)
        data = resp.json()
    except Exception as exc:
        print(f"get_bookings_by_terminal_id failed: {exc}")
        return "Failed to fetch bookings for the terminal. Please try again."

    # Response: { bookings: [ { id, status, carrier: { companyName, user: {email,phone} },
    #   terminal: { name, code, type }, timeSlot: { date, startTime, endTime },
    #   truck: { plateNumber, truckType, driverName } } ] }
    bookings = data.get("bookings", [])
    if not bookings:
        return f"No bookings found for this terminal ({start_date} to {end_date})."

    lines = []
    for b in bookings:
        booking_id = b.get("id", "UNKNOWN")
        b_status = b.get("status", "UNKNOWN")
        time_slot = b.get("timeSlot", {}) or {}
        slot_date = time_slot.get("date", "")
        if slot_date and "T" in str(slot_date):
            slot_date = str(slot_date).split("T")[0]
        start_time = time_slot.get("startTime", "")
        end_time = time_slot.get("endTime", "")
        carrier = b.get("carrier", {}) or {}
        company = carrier.get("companyName", "Unknown carrier")
        truck = b.get("truck", {}) or {}
        plate = truck.get("plateNumber", "N/A")
        driver = truck.get("driverName", "N/A")
        lines.append(
            f"- [{b_status}] {slot_date} {start_time}-{end_time} | Carrier: {company} | Truck: {plate} | Driver: {driver} | ID: {booking_id}"
        )

    max_items = 20
    total = len(lines)
    result = "\n".join(lines[:max_items])
    if total > max_items:
        result += f"\n...and {total - max_items} more bookings."
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Capacity by terminal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@tool
def get_capacity_by_terminal_id(
    terminal_id: str,
    date: str = "TODAY",
) -> str:
    """
    Fetch capacity config for a specific terminal on a given date
    via GET /api/terminals/:id/capacity-for-date?date=YYYY-MM-DD.
    Enriches with slot-level analytics from GET /api/analytics/terminals/:id/day-summary.

    Args:
        terminal_id: Terminal UUID (from operator's state).
        date: Date in YYYY-MM-DD format, or "TODAY" / "TOMORROW".
    """
    date = _resolve_date(date)

    try:
        resp = api_get(
            f"/api/terminals/{terminal_id}/capacity-for-date",
            params={"date": date},
        )
        data = resp.json()
    except Exception as exc:
        print(f"get_capacity_by_terminal_id failed: {exc}")
        return f"Failed to fetch capacity data for {date}."

    # Response when closed: { date, dayOfWeek, isClosed: true, closedReason, source: "CLOSED_DATE" }
    if data.get("isClosed"):
        reason = data.get("closedReason", "No reason provided")
        return f"Terminal is CLOSED on {date}. Reason: {reason}"

    # Response when open: { date, dayOfWeek, isClosed: false,
    #   operatingStart, operatingEnd, slotDurationMin, maxTrucksPerSlot,
    #   source: "OVERRIDE"|"DEFAULT_CONFIG", [overrideLabel, overrideId] }
    source = data.get("source", "UNKNOWN")
    operating_start = data.get("operatingStart", "N/A")
    operating_end = data.get("operatingEnd", "N/A")
    slot_duration = data.get("slotDurationMin", "N/A")
    max_trucks = data.get("maxTrucksPerSlot", "N/A")

    output = [
        f"--- CAPACITY FOR {date} ---",
        f"Source: {source}",
        f"Operating hours: {operating_start} - {operating_end}",
        f"Slot duration: {slot_duration} min",
        f"Max trucks per slot: {max_trucks}",
    ]

    # Enrich with slot-level analytics data
    try:
        analytics_resp = api_get(
            f"/api/analytics/terminals/{terminal_id}/day-summary",
            params={"date": date},
        )
        analytics_data = analytics_resp.json()
        # Response: { summaries: [ { terminal: {code,name}, slots: [
        #   { startTime, endTime, booked, capacity, available, isAvailable } ] } ] }
        summaries = analytics_data.get("summaries", [])
        if summaries:
            summary = summaries[0]
            slots = summary.get("slots", [])
            if slots:
                output.append("\nSlot breakdown:")
                for slot in slots:
                    s = slot.get("startTime", "")
                    e = slot.get("endTime", "")
                    booked = slot.get("booked", 0)
                    capacity = slot.get("capacity", 0)
                    available = slot.get("available", 0)
                    is_avail = slot.get("isAvailable", True)
                    status = "FULL" if (not is_avail or available <= 0) else "AVAILABLE"
                    output.append(
                        f"  {s} - {e} | booked: {booked} | available: {available} | max: {capacity} | {status}"
                    )
    except Exception:
        pass  # Analytics data is optional enrichment

    return "\n".join(output)
