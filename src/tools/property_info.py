import asyncio
import json
import logging
from pathlib import Path

from src.observability import tool_span

logger = logging.getLogger(__name__)
_DATA = Path(__file__).parent.parent / "data"


async def get_property_info(property_id: str, category: str) -> dict:
    """
    Return property-specific information for a given category.

    Valid categories: amenities, pet_policy, parking, lease_terms, utilities,
    move_in_costs, application_process, neighborhood, office_hours.

    Returns a dict with keys:
        property_id: echoed back
        category: echoed back
        info: the requested information as a string or nested dict
    Call this before answering any questions about the property features or policies.
    """
    try:
        async with tool_span(logger, "get_property_info", property_id=property_id, category=category):
            async with asyncio.timeout(2.0):
                def _read():
                    with open(_DATA / "properties.json") as f:
                        return json.load(f)
                properties: dict = await asyncio.to_thread(_read)       # for file sync operations (avoids main thread from blocking)

            if property_id not in properties:
                return {"error": f"property '{property_id}' not found"}

            prop = properties[property_id]

            if category not in prop:
                return {
                    "error": f"category '{category}' not available for this property",
                    "valid_categories": [
                        k for k in prop
                        if k not in ("name", "address", "phone")
                    ],
                }

            return {"property_id": property_id, "category": category, "info": prop[category]}

    except asyncio.TimeoutError:
        return {"error": "property info lookup timed out"}
    except Exception as exc:
        return {"error": str(exc)}
