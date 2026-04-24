from livekit.agents import function_tool

from src.agents.base import LeasingAgent
from src.agents.prompts import OUTBOUND_SYSTEM_PROMPT
from src.tools.scheduling import confirm_appointment, reschedule_appointment

# Agent responsible for confirming and rescheduling appointments 
# after the call has been scheduled by the inbound agent
class OutboundLeasingAgent(LeasingAgent):
    def __init__(self) -> None:
        super().__init__(instructions=OUTBOUND_SYSTEM_PROMPT)

    @function_tool
    async def confirm_appointment(self, appointment_id: str, status: str) -> dict:
        """
        Update the status of an existing tour appointment,
        This is called after the prospect verbally confirms or cancels.
        """
        return await confirm_appointment(appointment_id=appointment_id, status=status)

    @function_tool
    async def reschedule_appointment(self, appointment_id: str, new_date: str, new_time: str) -> dict:
        """
        Move an existing appointment to a new date and time,
        Checks for scheduling conflicts before updating.
        """
        return await reschedule_appointment(appointment_id=appointment_id, new_date=new_date, new_time=new_time)