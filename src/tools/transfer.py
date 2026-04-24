async def transfer_to_human(reason: str, summary: str) -> dict:
    """
    Escalate the current call to a human leasing agent.

    Returns a dict with keys:
        transferred: True if the handoff was initiated successfully
        reason: echoed back
        message: human-readable confirmation to read to the caller
    """
    # TODO: emit a LiveKit data message or room event so the human agent UI
    #       is notified and can join the room (SIP transfer or room bridge).
    # TODO: log the transfer with reason + summary for the human agent's context panel.

    return {
        "transferred": True,
        "reason": reason,
        "message": "I'm connecting you with a leasing agent now. Please hold on for a moment."
    }
