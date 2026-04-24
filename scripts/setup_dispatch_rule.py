"""
One-time script to create the SIP dispatch rule that routes inbound calls
on the trunk to a new room per call. Should trigger once after setting up the trunk.
"""
import asyncio
import os

from dotenv import load_dotenv
from livekit import api as lkapi

load_dotenv()


async def main() -> None:
    client = lkapi.LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )

    rule = await client.sip.create_dispatch_rule(
        lkapi.CreateSIPDispatchRuleRequest(
            trunk_ids=[os.environ["SIP_TRUNK_ID"]],
            rule=lkapi.SIPDispatchRule(
                dispatch_rule_individual=lkapi.SIPDispatchRuleIndividual(
                    room_prefix="call-",
                )
            ),
            name="leasing-agent-inbound",
        )
    )

    print(f"Dispatch rule created: {rule.sip_dispatch_rule_id}")
    await client.aclose()


asyncio.run(main())
