import json
import logging
import time
from dotenv import load_dotenv

from livekit.agents import (
    AgentSession,
    JobContext,
    RoomInputOptions,
    WorkerOptions,
    cli,
    llm,
    stt,
    tts,
    inference
)
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from src.agents.inbound import InboundLeasingAgent
from src.agents.outbound import OutboundLeasingAgent
from src.observability import bind_session, log_metrics, setup_logging

load_dotenv()
setup_logging()

logger = logging.getLogger(__name__)


def create_session() -> AgentSession:
    # FallbackAdapter tries the primary model first; falls back to secondary on failure
    return AgentSession(
        stt = stt.FallbackAdapter(
            [
                inference.STT.from_model_string("deepgram/nova-3"),
                inference.STT.from_model_string("deepgram/nova-2"),
            ]
        ),
        llm=llm.FallbackAdapter(
            [
                inference.LLM.from_model_string("openai/gpt-4o-mini"),
                inference.LLM.from_model_string("openai/gpt-5-nano"),
            ]
        ),
        tts=tts.FallbackAdapter(
            [
                inference.TTS.from_model_string("cartesia/sonic-2"),
                inference.TTS.from_model_string("cartesia/sonic-1"),
            ]
        ),
        vad=silero.VAD.load(),                  # Silero detects speech (starts and stops)
        turn_detection=MultilingualModel(),     # decides when the caller has finished speaking
    )


async def entrypoint(ctx: JobContext) -> None:
    # ctx.job.metadata is a JSON blob set by the caller (me in SIP on LiveKit dashboard).
    metadata = json.loads(ctx.job.metadata) if ctx.job.metadata else {}

    # If appointment_id present -> outbound confirmation call -> OutboundLeasingAgent
    if metadata.get("appointment_id"):
        agent = OutboundLeasingAgent()
    else:
        agent = InboundLeasingAgent()

    # Stamp every log in this call with the room name so the full session is grep-able
    bind_session(ctx.room.name)

    session = create_session()

    @session.on("metrics_collected")
    def on_metrics(event) -> None:
        log_metrics(event)

    await ctx.connect()         # joins the LiveKit Room (the call's audio channel)

    agent_type = type(agent).__name__
    t0 = time.monotonic()
    logger.info("call.started", extra={"agent": agent_type})

    try:
        await session.start(
            agent=agent,
            room=ctx.room,
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        )
    finally:
        logger.info(
            "call.completed",
            extra={
                "agent": agent_type,
                "duration_s": round(time.monotonic() - t0),
            },
        )


# cli.run_app() starts a LiveKit Worker which is a long-running process
# that registers with LiveKit server (URL + API key from .env) and sits idle waiting for jobs to be dispatched.
if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            max_retry=3,
        )
    )
