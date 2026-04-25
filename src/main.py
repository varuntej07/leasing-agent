import logging
import time
from dotenv import load_dotenv

from livekit.agents import (
    AgentSession,
    JobContext,
    WorkerOptions,
    JobProcess,
    TurnHandlingOptions,
    cli,
    llm,
    stt,
    tts,
    inference,
)
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents.voice.room_io import RoomOptions, AudioInputOptions

from src.agents.inbound import InboundLeasingAgent
from src.observability import bind_session, setup_logging
from src.session import SessionHandler

load_dotenv()

logger = logging.getLogger(__name__)


# Runs once per worker process before any sessions start
# It loads the Silero VAD model into memory and stores it in proc.userdata so future sessions reuse the same instance
def prewarm(process: JobProcess) -> None:
    setup_logging()
    process.userdata["vad"] = silero.VAD.load()
    logging.getLogger(__name__).info("prewarm complete, models loaded")


def create_session(vad: silero.VAD) -> AgentSession:
    # FallbackAdapter tries the primary model first; falls back to secondary on failure
    return AgentSession(
        stt=stt.FallbackAdapter(
            [
                inference.STT.from_model_string("deepgram/nova-3"),
                inference.STT.from_model_string("deepgram/nova-2"),
            ]
        ),
        llm=llm.FallbackAdapter(
            [
                inference.LLM.from_model_string("openai/gpt-4o-mini"),
                inference.LLM.from_model_string("openai/gpt-4o"),
            ]
        ),
        tts=tts.FallbackAdapter(
            [
                inference.TTS.from_model_string("cartesia/sonic-2"),
                inference.TTS.from_model_string("cartesia/sonic-1"),
            ]
        ),
        vad=vad,                                # prewarmed in prewarm(); doesn't need to load again
        turn_handling=TurnHandlingOptions(
            turn_detection=MultilingualModel(),      # decides when the caller has finished speaking
            endpointing={
                "mode": "dynamic",        # agent adapts delay within min_delay & max_delay based on session pause statistics
                "min_delay": 0.4,
                "max_delay": 1.6,
            },
            interruption={
                # Accept barge-in earlier so callers do not need to wait through a full sentence.
                "min_duration": 0.25,
                "min_words": 1,
                "resume_false_interruption": True,
                "false_interruption_timeout": 1.0,
            },
        ),
    )


async def entrypoint(ctx: JobContext) -> None:
    agent = InboundLeasingAgent()

    # stamps every log in this call with the room name so the full session is greppable
    bind_session(ctx.room.name)

    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()
    session = create_session(vad=vad)
    handler = SessionHandler(session=session, ctx=ctx)

    await ctx.connect()

    agent_type = type(agent).__name__
    t0 = time.monotonic()
    logger.info("call.started", extra={"agent": agent_type})

    try:
        await session.start(
            agent=agent,
            room=ctx.room,
            room_options=RoomOptions(
                audio_input=AudioInputOptions(
                    noise_cancellation=noise_cancellation.BVC(),
                )
            ),
            # sends traces, logs, transcript, and audio to LiveKit Cloud Insights dashboard
            record=True,
        )
        await ctx.wait_for_participant()
        opening_handle = session.generate_reply(
            instructions="Begin the call now with your required inbound greeting and offer assistance."
        )
        await opening_handle.wait_for_playout()
        await session.wait_for_inactive()
    finally:
        logger.info(
            "call.completed",
            extra={
                "agent": agent_type,
                "duration_s": round(time.monotonic() - t0),
            },
        )
        handler.flush_usage()


# cli.run_app() starts a LiveKit Worker which is a long-running process
# that registers with LiveKit server (URL + API key from .env) and sits idle waiting for jobs to be dispatched.
if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            max_retry=3,
        )
    )
