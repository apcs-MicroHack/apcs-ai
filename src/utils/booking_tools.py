"""Booking tools for the Booking Agent."""
import json
import datetime
from typing import Optional
from langchain_core.tools import tool
from src.utils.api_client import api_get, get_base_url, get_auth, refresh_tokens
from src.utils.capacity_tools import get_terminals_map


@tool
def get_bookings_by_user(
    user_id: str = "",
    user_role: str = "CARRIER",
    status: Optional[str] = None,
    terminal_id: Optional[str] = None,
    carrier_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    Fetch bookings from the backend API.
    - CARRIER: returns only the carrier's own bookings.
    - ADMIN: returns ALL bookings system-wide. Optionally filter by terminal or carrier.
    user_id and user_role are injected by the system; do not guess them.

    Args:
        status: Filter by status. PENDING, CONFIRMED, CONSUMED, CANCELLED, REJECTED (UPPERCASE).
        terminal_id: Filter by terminal UUID (ADMIN only — carriers are scoped automatically).
        carrier_id: Filter by carrier UUID (ADMIN only).
        start_date: Filter from date (YYYY-MM-DD). Defaults to today if omitted.
        end_date: Filter to date (YYYY-MM-DD). Defaults to today+7 if omitted.
    """
    today = datetime.date.today()
    start_date = _resolve_date(start_date) if start_date else today.strftime("%Y-%m-%d")
    end_date = _resolve_date(end_date) if end_date else (today + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    normalized_status = status.upper().strip() if status else None

    query: dict = {
        "startDate": start_date,
        "endDate": end_date,
    }

    if normalized_status:
        query["status"] = normalized_status

    # Role-based query building
    if user_role == "ADMIN":
        # Admin sees all bookings; optionally narrow by terminal or carrier
        if terminal_id:
            query["terminalId"] = terminal_id
        if carrier_id:
            query["carrierId"] = carrier_id
    else:
        # CARRIER / OPERATOR — AI API uses admin JWT, so the backend won't auto-scope.
        # We MUST pass carrierId explicitly so the backend filters correctly.
        if carrier_id:
            query["carrierId"] = carrier_id
        if terminal_id:
            query["terminalId"] = terminal_id

    try:
        resp = api_get("/api/bookings", params=query)
        data = resp.json()
    except Exception as exc:
        print(f"get_bookings_by_user failed: {exc}")
        return "Failed to fetch bookings. Please try again."

    bookings = data.get("bookings", [])
    if not bookings:
        return "No bookings found matching your filters."

    normalized = []
    for booking in bookings:
        booking_id = booking.get("id") or booking.get("bookingId") or "UNKNOWN"
        b_status = booking.get("status", "UNKNOWN")
        time_slot = booking.get("timeSlot", {}) or {}
        slot_date = time_slot.get("date", "")
        if slot_date and "T" in str(slot_date):
            slot_date = str(slot_date).split("T")[0]
        start_time = time_slot.get("startTime", "")
        end_time = time_slot.get("endTime", "")
        terminal = booking.get("terminal", {}) or {}
        terminal_name = terminal.get("name") or terminal.get("code") or ""
        truck = booking.get("truck", {}) or {}
        plate = truck.get("plateNumber", "")
        carrier = booking.get("carrier", {}) or {}
        company = carrier.get("companyName", "")

        line = f"- [{b_status}] {slot_date} {start_time}-{end_time} | Terminal: {terminal_name}"
        if company:
            line += f" | Carrier: {company}"
        if plate:
            line += f" | Truck: {plate}"
        line += f" | ID: {booking_id}"
        normalized.append(line)

    max_items = 15
    total = len(normalized)
    result = "\n".join(normalized[:max_items])
    if total > max_items:
        result += f"\n...and {total - max_items} more bookings."
    return result


@tool
def get_all_bookings(
    status: Optional[str] = None,
    terminal_id: Optional[str] = None,
    carrier_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    ADMIN-ONLY: Fetch all bookings system-wide from GET /api/bookings.
    Returns bookings across all terminals and carriers. Use optional filters to narrow results.

    Args:
        status: Filter by status — PENDING, CONFIRMED, CONSUMED, CANCELLED, REJECTED (UPPERCASE).
        terminal_id: Filter by a specific terminal UUID. Omit to get all terminals.
        carrier_id: Filter by a specific carrier UUID. Omit to get all carriers.
        start_date: Filter from date (YYYY-MM-DD). Defaults to today.
        end_date: Filter to date (YYYY-MM-DD). Defaults to today + 3 days.
    """
    today = datetime.date.today()
    start_date = _resolve_date(start_date) if start_date else today.strftime("%Y-%m-%d")
    end_date = _resolve_date(end_date) if end_date else (today + datetime.timedelta(days=3)).strftime("%Y-%m-%d")

    normalized_status = status.upper().strip() if status else None

    params: dict = {
        "startDate": start_date,
        "endDate": end_date,
    }
    if normalized_status:
        params["status"] = normalized_status
    if terminal_id:
        params["terminalId"] = terminal_id
    if carrier_id:
        params["carrierId"] = carrier_id

    try:
        resp = api_get("/api/bookings", params=params)
        data = resp.json()
    except Exception as exc:
        print(f"get_all_bookings failed: {exc}")
        return "Failed to fetch bookings. Please try again."

    bookings = data.get("bookings", [])
    if not bookings:
        return f"No bookings found ({start_date} to {end_date})."

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
        terminal = b.get("terminal", {}) or {}
        terminal_name = terminal.get("name") or terminal.get("code") or "N/A"
        carrier = b.get("carrier", {}) or {}
        company = carrier.get("companyName", "N/A")
        truck = b.get("truck", {}) or {}
        plate = truck.get("plateNumber", "N/A")
        driver = truck.get("driverName", "N/A")

        lines.append(
            f"- [{b_status}] {slot_date} {start_time}-{end_time} | Terminal: {terminal_name} | Carrier: {company} | Truck: {plate} | Driver: {driver} | ID: {booking_id}"
        )

    max_items = 25
    total = len(lines)
    result = f"Total bookings: {total}\n" + "\n".join(lines[:max_items])
    if total > max_items:
        result += f"\n...and {total - max_items} more bookings."
    return result


@tool
def check_availability(terminal_id: str, start_date: str, end_date: str):
    """Check slot availability for a terminal over a date range.

    Args:
        terminal_id: Terminal UUID (use get_terminals_map to resolve names).
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
    """
    start_date = _resolve_date(start_date)
    end_date = _resolve_date(end_date)

    try:
        resp = api_get("/api/slots/available", params={
            "terminalId": terminal_id,
            "startDate": start_date,
            "endDate": end_date,
        })
        data = resp.json()
    except Exception as exc:
        print(f"check_availability failed: {exc}")
        return "Failed to check availability. Please try again."

    if not isinstance(data, dict):
        return "No availability data returned."

    availability = data.get("availability", [])
    if not isinstance(availability, list) or not availability:
        return "No availability data found for the given dates."

    output = [f"--- AVAILABILITY REPORT: {start_date} to {end_date} ---"]

    for day in availability:
        day_date = day.get("date", "unknown")

        if day.get("isClosed"):
            output.append(f"\n{day_date}: TERMINAL CLOSED")
            continue

        slots = day.get("slots", [])
        if not slots:
            output.append(f"\n{day_date}: No slots configured.")
            continue

        total_capacity = 0
        total_available = 0
        best_slot = None
        best_avail = 0
        slot_lines = []

        for slot in slots:
            s_time = slot.get("startTime") or slot.get("start_time", "")
            e_time = slot.get("endTime") or slot.get("end_time", "")
            is_avail = slot.get("isAvailable", True)
            avail = slot.get("availableCapacity", slot.get("available", 0))
            cap = slot.get("capacity", slot.get("maxCapacity", avail))

            total_capacity += cap
            total_available += avail if (is_avail and avail > 0) else 0

            if not is_avail or avail <= 0:
                slot_lines.append(f"  {s_time}-{e_time} | FULL")
            else:
                pct = (avail / cap * 100) if cap > 0 else 0
                tag = "LOW" if pct < 30 else "OK"
                slot_lines.append(f"  {s_time}-{e_time} | {avail}/{cap} slots ({tag})")
                if avail > best_avail:
                    best_avail = avail
                    best_slot = f"{s_time}-{e_time}"

        saturation = ((total_capacity - total_available) / total_capacity * 100) if total_capacity > 0 else 0
        output.append(f"\n{day_date} | {saturation:.0f}% booked | {total_available}/{total_capacity} free")
        output.extend(slot_lines)
        if best_slot:
            output.append(f"  Best slot: {best_slot} ({best_avail} available)")

    return "\n".join(output)


@tool
def prepare_booking_form(date: str, time: str, terminal: str):
    """
    Generate structured UI payload to open the booking form.
    Only call this when date, time, and terminal are ALL provided.

    Args:
        date: Booking date in YYYY-MM-DD format.
        time: Booking start time in HH:mm format.
        terminal: Terminal name or ID.
    """
    # Resolve terminal name to UUID
    terminals_map = get_terminals_map.invoke({})
    terminal_id = terminals_map.get(terminal) or terminal  # fallback to original if not found

    return json.dumps({
        "ui_action": "OPEN_BOOKING_FORM",
        "prefill": {"date": date, "time": time, "terminal": terminal, "terminal_id": terminal_id}
    })


@tool
def get_terminal_schedule(
    date: str = "TODAY",
    terminal_id: str = "ALL",
):
    """[OPERATOR TOOL] Returns the schedule/density for a terminal on a date.

    Args:
        date: Date in YYYY-MM-DD, or "TODAY" / "TOMORROW".
        terminal_id: Terminal UUID, or "ALL".
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
        print(f"get_terminal_schedule failed: {exc}")
        return f"--- SCHEDULE FOR {date} ---\nNo data available."

    summaries = data.get("summaries", [])
    if not summaries:
        return f"--- SCHEDULE FOR {date} ---\nNo data available."

    output = [f"--- SCHEDULE FOR {date} ---"]
    for summary in summaries:
        terminal = summary.get("terminal", {})
        code = terminal.get("code") or terminal.get("name") or "UNKNOWN"
        output.append(f"\nTerminal {code}:")
        for slot in summary.get("slots", []):
            s = slot.get("startTime", "")
            e = slot.get("endTime", "")
            booked = slot.get("booked", 0)
            cap = slot.get("capacity", 0)
            avail = slot.get("available", 0)
            status = "FULL" if (not slot.get("isAvailable", True) or avail <= 0) else "AVAILABLE"
            output.append(f"  {s} - {e} | booked: {booked} | available: {avail} | max: {cap} | {status}")

    return "\n".join(output)


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
