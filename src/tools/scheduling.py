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


def _load_tours() -> list[dict]:
    with open(_TOURS) as f:
        return json.load(f)


def _save_tours(tours: list[dict]) -> None:
    _TOURS.write_text(json.dumps(tours, indent=2))


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
                tours = _load_tours()

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
                _save_tours(tours)

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


async def confirm_appointment(appointment_id: str, status: str) -> dict:
    """
    Update the status of an existing appointment to "confirmed" or "cancelled".

    Returns a dict with keys:
        success: True if the appointment was found and updated
        appointment_id: echoed back
        status: the new status
        message: human-readable result to read to the caller
    """
    try:
        async with tool_span(logger, "confirm_appointment", appointment_id=appointment_id, status=status):
            if status not in ("confirmed", "cancelled"):
                return {"success": False, "error": f"invalid status '{status}'; must be 'confirmed' or 'cancelled'"}

            async with asyncio.timeout(3.0):
                tours = _load_tours()
                appt = next((t for t in tours if t["appointment_id"] == appointment_id), None)

                if appt is None:
                    return {"success": False, "error": f"appointment '{appointment_id}' not found"}

                appt["status"] = status
                _save_tours(tours)

            action = "confirmed" if status == "confirmed" else "cancelled"
            return {
                "success": True,
                "appointment_id": appointment_id,
                "status": status,
                "message": f"Your appointment has been {action}.",
            }

    except asyncio.TimeoutError:
        return {"success": False, "error": "confirmation request timed out"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def reschedule_appointment(
    appointment_id: str,
    new_date: str,
    new_time: str,
) -> dict:
    """
    Move an existing appointment to a new date and time.
    Checks for conflicts at the new slot before updating.

    Returns a dict with keys:
        success: True if the appointment was moved
        appointment_id: echoed back
        new_date: confirmed new date
        new_time: confirmed new time
        message: human-readable result to read to the caller
    """
    try:
        async with tool_span(
            logger,
            "reschedule_appointment",
            appointment_id=appointment_id,
            new_date=new_date,
            new_time=new_time,
        ):
            async with asyncio.timeout(3.0):
                tours = _load_tours()
                appt = next((t for t in tours if t["appointment_id"] == appointment_id), None)

                if appt is None:
                    return {"success": False, "error": f"appointment '{appointment_id}' not found"}

                if _has_conflict(tours, appt["property_id"], new_date, new_time, exclude_id=appointment_id):
                    return {
                        "success": False,
                        "message": f"That new slot is already taken. Please choose a different date or time.",
                    }

                appt["date"] = new_date
                appt["time"] = new_time
                _save_tours(tours)

            return {
                "success": True,
                "appointment_id": appointment_id,
                "new_date": new_date,
                "new_time": new_time,
                "message": f"Your tour has been moved to {new_date} at {new_time}.",
            }

    except asyncio.TimeoutError:
        return {"success": False, "error": "reschedule request timed out"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
