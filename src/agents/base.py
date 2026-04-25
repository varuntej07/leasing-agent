from livekit.agents import Agent, function_tool
from livekit.agents.beta.tools import EndCallTool

from src.tools.transfer import transfer_to_human as _transfer_to_human


# shared base for all leasing agent types so common tools live in one place
class LeasingAgent(Agent):
    def __init__(self, instructions: str) -> None:
        end_call_tool = EndCallTool(
            extra_description=(
                "Use this when the conversation is complete, when the caller clearly says goodbye, "
                "or after you give emergency safety instructions and there is nothing else essential to collect."
            ),
            delete_room=True,
            end_instructions=(
                "Give one short, natural closing line for a phone call and end the call. "
                "Do not ask any new follow-up question."
            ),
        )
        super().__init__(instructions=instructions, tools=end_call_tool.tools)

    @function_tool
    async def transfer_to_human(self, reason: str, summary: str) -> dict:
        """
        Escalate the call to a human leasing agent.
        Use only for billing or rent payment questions, or when the caller explicitly
        asks to speak with a person. Do NOT use for maintenance requests - handle
        those with submit_maintenance_request instead.

        Args:
            reason:  Short label for why the call is being transferred
                     (e.g."caller_request").
            summary: One-sentence summary of what the caller needs so the human
                     agent is not starting from scratch.
        """
        # takes reason and summary, hands the call off to a live agent
        return await _transfer_to_human(reason=reason, summary=summary)
