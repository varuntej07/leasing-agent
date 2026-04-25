import asyncio
import json
import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

from src.observability import tool_span

logger = logging.getLogger(__name__)
_DATA = Path(__file__).parent.parent / "data"
_TOURS = _DATA / "tours.json"


async def _load_tours() -> list[dict]:
    def _read():
        with open(_TOURS) as f:
            return json.load(f)
    return await asyncio.to_thread(_read)


async def _save_tours(tours: list[dict]) -> None:
    # Write to a temp file then atomically replace to avoid corrupt JSON on crash
    payload = json.dumps(tours, indent=2)
    def _write():
        tmp = _TOURS.with_suffix(".tmp")
        tmp.write_text(payload)
        tmp.replace(_TOURS)
    await asyncio.to_thread(_write)


def _has_conflict(tours: list[dict], property_id: str, date: str, time: str, exclude_id: str = "") -> bool:
    return any(
        t["property_id"] == property_id
        and t["date"] == date
        and t["time"] == time
        and t["status"] != "cancelled"
        and t["appointment_id"] != exclude_id
        for t in tours
    )


async def schedule_tour(
    property_id: str,
    date: str,
    time: str,
    caller_name: str,
    caller_phone: str,
    unit_id: Optional[str] = None,
    caller_email: Optional[str] = None,
) -> dict:
    """
    Book a tour appointment at a property after verifying no scheduling conflict exists.

    Returns a dict with keys:
        success: True if the appointment was created
        appointment_id: unique ID for the new appointment
        property_id: echoed back
        date: confirmed date (YYYY-MM-DD)
        time: confirmed time (HH:MM)
        message: human-readable confirmation to read to the caller
    """
    try:
        async with tool_span(
            logger,
            "schedule_tour",
            property_id=property_id,
            date=date,
            time=time,
        ):
            async with asyncio.timeout(3.0):
                tours = await _load_tours()

                if _has_conflict(tours, property_id, date, time):
                    return {
                        "success": False,
                        "message": f"That time slot is already taken at this property. Please choose a different date or time.",
                    }

                appointment_id = "apt-" + uuid4().hex[:8]
                tours.append({
                    "appointment_id": appointment_id,
                    "property_id": property_id,
                    "unit_id": unit_id,
                    "date": date,
                    "time": time,
                    "prospect_name": caller_name,
                    "prospect_phone": caller_phone,
                    "prospect_email": caller_email,
                    "status": "scheduled",
                })
                await _save_tours(tours)

            return {
                "success": True,
                "appointment_id": appointment_id,
                "property_id": property_id,
                "date": date,
                "time": time,
                "message": f"Your tour is confirmed for {date} at {time}. Your appointment ID is {appointment_id}.",
            }

    except asyncio.TimeoutError:
        return {"success": False, "error": "scheduling request timed out"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
