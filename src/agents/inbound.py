from typing import Optional

from livekit.agents import function_tool

from src.agents.base import LeasingAgent
from src.agents.prompts import INBOUND_SYSTEM_PROMPT
from src.tools.availability import check_availability
from src.tools.property_info import get_property_info
from src.tools.scheduling import schedule_tour


class InboundLeasingAgent(LeasingAgent):
    def __init__(self) -> None:
        super().__init__(instructions=INBOUND_SYSTEM_PROMPT)

    @function_tool
    async def check_availability(
        self,
        property_id: str,                    # ID of the property (e.g. "cascade-heights")
        unit_type: Optional[str] = None,     # "studio", "1bed", "2bed", or "3bed"
        move_in_date: Optional[str] = None,  # YYYY-MM-DD format
        max_rent: Optional[float] = None,    # maximum monthly rent the caller can afford
    ) -> dict:
        """
        Checks which units are currently available at a property.
        """
        return await check_availability(
            property_id=property_id,
            unit_type=unit_type,
            move_in_date=move_in_date,
            max_rent=max_rent,
        )

    @function_tool
    async def schedule_tour(
        self,
        property_id: str,
        date: str,                               # requested tour date in YYYY-MM-DD format
        time: str,                               # requested tour time in HH:MM (24-hour) format
        caller_name: str,                        # full name of the prospective tenant
        caller_phone: str,                       # callback phone number for the prospect
        unit_id: Optional[str] = None,           # optional specific unit the caller wants to tour
        caller_email: Optional[str] = None,      # optional email address for the confirmation
    ) -> dict:
        """
        Book a tour appointment at a property.
        Requires caller_name and caller_phone before calling.
        Never confirms a booking to the caller without a successful response from this tool.
        """
        # takes caller details and preferred slot, returns a confirmation id on success
        return await schedule_tour(
            property_id=property_id,
            date=date,
            time=time,
            caller_name=caller_name,
            caller_phone=caller_phone,
            unit_id=unit_id,
            caller_email=caller_email,
        )

    @function_tool
    async def get_property_info(
        self,
        property_id: str,
        category: str,
    ) -> dict:
        """
        Retrieve property-specific information by category.
        """
        return await get_property_info(property_id=property_id, category=category)
