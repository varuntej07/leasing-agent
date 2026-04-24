from livekit.agents import Agent, function_tool

from src.tools.transfer import transfer_to_human as _transfer_to_human


# shared base for all leasing agent types so common tools live in one place
class LeasingAgent(Agent):
    def __init__(self, instructions: str) -> None:
        super().__init__(instructions=instructions)

    @function_tool
    async def transfer_to_human(self, reason: str, summary: str) -> dict:
        """
        Escalate the call to a human leasing agent.
        Useful for maintenance requests, billing questions, or when the caller asks
        to speak with a person.

        Args:
            reason:  Short label for why the call is being transferred
                     (e.g. "maintenance_request", "billing_question", "caller_request").
            summary: One-sentence summary of what the caller needs so the human
                     agent is not starting from scratch.
        """
        # takes reason and summary, hands the call off to a live agent
        return await _transfer_to_human(reason=reason, summary=summary)
