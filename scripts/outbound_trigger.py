"""
Script to trigger an outbound confirmation call via LiveKit SIP.

Usage:
    python scripts/outbound_trigger.py --appointment-id t-001 --phone +12065550911

How it works:
    1. Looks up the appointment in src/data/tours.json.
    2. Creates a LiveKit room and dispatches the leasing-agent worker with appointment context.
    3. Creates a SIP participant to dial the prospect's phone number via the SIP trunk.

Prerequisites:
    - A leasing-agent worker is running: `python -m src.main dev`
    - LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET are set in .env
    - SIP_TRUNK_ID is set in .env (LiveKit SIP trunk configured for outbound calls)
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit import api

load_dotenv()

TOURS_FILE = Path(__file__).parent.parent / "src" / "data" / "tours.json"


def load_appointment(appointment_id: str) -> dict:
    appointments = json.loads(TOURS_FILE.read_text())
    for appt in appointments:
        if appt["appointment_id"] == appointment_id:
            return appt
    raise ValueError(f"Appointment {appointment_id!r} not found in tours.json")


async def trigger_outbound_call(appointment_id: str, phone: str) -> None:
    appointment = load_appointment(appointment_id)
    print(f"Found appointment: {appointment}")

    room_name = f"outbound-{appointment_id}"

    async with api.LiveKitAPI(
        os.environ["LIVEKIT_URL"],
        os.environ["LIVEKIT_API_KEY"],
        os.environ["LIVEKIT_API_SECRET"],
    ) as lk:
        await lk.room.create_room(api.CreateRoomRequest(name=room_name))
        print(f"Created room: {room_name}")

        await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="leasing-agent",
                room=room_name,
                metadata=json.dumps({"appointment_id": appointment_id}),
            )
        )
        print(f"Dispatched leasing-agent to room {room_name}")

        await lk.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=os.environ["SIP_TRUNK_ID"],
                sip_call_to=phone,
                room_name=room_name,
            )
        )
        print(f"Dialing {phone} via LiveKit SIP...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trigger an outbound confirmation call.")
    parser.add_argument("--appointment-id", required=True, help="ID from tours.json")
    parser.add_argument("--phone", required=True, help="E.164 phone number to call")
    args = parser.parse_args()

    asyncio.run(trigger_outbound_call(args.appointment_id, args.phone))
