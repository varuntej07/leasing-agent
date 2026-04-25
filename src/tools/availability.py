import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from src.observability import tool_span

logger = logging.getLogger(__name__)
_DATA = Path(__file__).parent.parent / "data"


async def check_availability(
    property_id: str,
    unit_type: Optional[str] = None,
    move_in_date: Optional[str] = None,
    max_rent: Optional[float] = None,
) -> dict:
    """
    Return available units at the given property, optionally filtered by type,
    move-in date, and maximum rent.

    Returns a dict with keys:
        available_units: list of unit dicts (unit_id, type, rent, sqft, floor,
                         available_date, floor_plan_url)
        property_id: echoed back for the caller's reference
    """
    try:
        async with tool_span(
            logger,
            "check_availability",
            property_id=property_id,
            unit_type=unit_type,
            move_in_date=move_in_date,
            max_rent=max_rent,
        ):
            async with asyncio.timeout(2.0):
                def _read():
                    with open(_DATA / "units.json") as f:
                        return json.load(f)
                units: list[dict] = await asyncio.to_thread(_read)

            known_properties = {"cascade-heights", "the-meridian", "pineview-commons"}
            if property_id not in known_properties:
                return {
                    "error": f"property '{property_id}' not found",
                    "available_units": [],
                    "count": 0,
                }

            results = [u for u in units if u["property_id"] == property_id]

            if unit_type:
                results = [u for u in results if u["type"] == unit_type]

            if max_rent is not None:
                results = [u for u in results if u["rent"] <= max_rent]

            if move_in_date:
                results = [
                    u for u in results
                    if u["available"]
                    and u["available_date"] is not None
                    and u["available_date"] <= move_in_date
                ]
            else:
                results = [u for u in results if u["available"]]

            return {
                "property_id": property_id,
                "available_units": results,
                "count": len(results),
            }

    except asyncio.TimeoutError:
        return {"error": "availability check timed out", "available_units": [], "count": 0}
    except Exception as exc:
        return {"error": str(exc), "available_units": [], "count": 0}
