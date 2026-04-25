import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.observability import tool_span

logger = logging.getLogger(__name__)
_DATA = Path(__file__).parent.parent / "data"
_REQUESTS = _DATA / "maintenance_requests.json"

VALID_ISSUE_TYPES = {"plumbing", "electrical", "appliance", "hvac", "structural", "pest", "other"}
VALID_URGENCY = {"emergency", "urgent", "routine"}


async def _load_requests() -> list[dict]:
    def _read():
        with open(_REQUESTS) as f:
            return json.load(f)
    return await asyncio.to_thread(_read)


async def _save_requests(requests: list[dict]) -> None:
    # Write to a temp file then atomically replace to avoid corrupt JSON on crash
    payload = json.dumps(requests, indent=2)
    def _write():
        tmp = _REQUESTS.with_suffix(".tmp")
        tmp.write_text(payload)
        tmp.replace(_REQUESTS)
    await asyncio.to_thread(_write)


async def submit_maintenance_request(
    property_id: str,
    unit_id: str,
    resident_name: str,
    resident_phone: str,
    issue_type: str,
    description: str,
    urgency: str,
) -> dict:
    """
    Log a maintenance or repair request for a unit and persist it to the
    property dashboard (maintenance_requests.json).

    Returns a dict with keys:
        success: True if the request was created
        request_id: unique ID for tracking
        urgency: echoed back
        message: human-readable confirmation to read to the caller
    """
    try:
        async with tool_span(
            logger,
            "submit_maintenance_request",
            property_id=property_id,
            unit_id=unit_id,
            issue_type=issue_type,
            urgency=urgency,
        ):
            async with asyncio.timeout(3.0):
                # Validate property exists
                def _read_properties():
                    with open(_DATA / "properties.json") as f:
                        return json.load(f)
                properties: dict = await asyncio.to_thread(_read_properties)

                if property_id not in properties:
                    logger.warning(
                        "tool.validation_error",
                        extra={"tool": "submit_maintenance_request", "field": "property_id", "value": property_id},
                    )
                    return {"success": False, "error": f"property '{property_id}' not found"}

                if issue_type not in VALID_ISSUE_TYPES:
                    logger.warning(
                        "tool.validation_error",
                        extra={"tool": "submit_maintenance_request", "field": "issue_type", "value": issue_type},
                    )
                    return {"success": False, "error": f"invalid issue_type '{issue_type}'"}

                if urgency not in VALID_URGENCY:
                    logger.warning(
                        "tool.validation_error",
                        extra={"tool": "submit_maintenance_request", "field": "urgency", "value": urgency},
                    )
                    return {"success": False, "error": f"invalid urgency '{urgency}'"}

                request_id = "req-" + uuid4().hex[:8]
                requests = await _load_requests()
                requests.append({
                    "request_id": request_id,
                    "property_id": property_id,
                    "unit_id": unit_id,
                    "resident_name": resident_name,
                    "resident_phone": resident_phone,
                    "issue_type": issue_type,
                    "description": description,
                    "urgency": urgency,
                    "status": "open",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                await _save_requests(requests)

            response_time = {
                "emergency": "immediately",
                "urgent": "within 24 hours",
                "routine": "within 3–5 business days",
            }[urgency]

            return {
                "success": True,
                "request_id": request_id,
                "urgency": urgency,
                "message": (
                    f"Your maintenance request has been logged. "
                    f"Your request ID is {request_id}. "
                    f"A technician will be in touch {response_time}."
                ),
            }

    except asyncio.TimeoutError:
        return {"success": False, "error": "maintenance request timed out"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
