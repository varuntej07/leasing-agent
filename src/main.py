import asyncio
import logging
import re
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
    AgentStateChangedEvent,
    metrics as lk_metrics,
    MetricsCollectedEvent,
    UserInputTranscribedEvent,
)
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents.voice.room_io import RoomOptions, AudioInputOptions

from src.agents.inbound import InboundLeasingAgent
from src.observability import bind_session, log_metrics, log_ttfa, log_turn_latency, setup_logging

load_dotenv()
setup_logging()

logger = logging.getLogger(__name__)

GOODBYE_RE = re.compile(
    r"\b(bye|goodbye|bye[- ]?bye|see you|see ya|talk to you later|that's all|that is all|that's it|that is it|no that's all|no that is all|no that's it|no that is it)\b"
)

# Runs once per worker process before any sessions start.
# It loads the Silero VAD model into memory and stores it in proc.userdata so future sessions reuse same instance
def prewarm(process: JobProcess):
    process.userdata["vad"] = silero.VAD.load()
    logging.info("Prewarm complete, models loaded", extra={"vad": process.userdata["vad"]})


def create_session(vad: silero.VAD) -> AgentSession:
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
    opening_instruction = "Begin the call now with your required inbound greeting and offer assistance."

    # Stamp every log in this call with the room name so the full session is grep-able
    bind_session(ctx.room.name)

    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()
    session = create_session(vad=vad)

    # single-element list so the closure can mutate without nonlocal; holds the full EOUMetrics object
    # for the current turn so both log_turn_latency and log_ttfa can read eou.timestamp and eou.speech_id
    _last_eou: list = []
    _idle_check_sent = False
    _forced_end_task: asyncio.Task[None] | None = None

    # accumulates token and character counts per model across all turns; flushed on call end
    usage_collector = lk_metrics.ModelUsageCollector()

    async def force_end_call(closing_line: str, reason: str) -> None:
        nonlocal _forced_end_task

        logger.info("call.fast_end.requested", extra={"reason": reason, "transcript_matched": True})

        try:
            handle = session.say(closing_line, allow_interruptions=False, add_to_chat_ctx=True)
            await handle.wait_for_playout()
        except Exception:
            logger.exception("call.fast_end.playout_failed", extra={"reason": reason})
        finally:
            try:
                await ctx.delete_room()
            except Exception:
                logger.exception("call.fast_end.delete_room_failed", extra={"reason": reason})

            session.shutdown(drain=False)
            ctx.shutdown(reason=reason)
            _forced_end_task = None

    @session.on("metrics_collected")
    def on_metrics(ev: MetricsCollectedEvent) -> None:
        log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)
        if ev.metrics.type == "eou_metrics":
            # overwrite previous turn's EOU; on_agent_state_changed clears this after TTFA is logged
            _last_eou[:] = [ev.metrics]
        elif ev.metrics.type == "llm_metrics" and _last_eou:
            eou = _last_eou[0]
            log_turn_latency(
                round(eou.end_of_utterance_delay * 1000),
                round(ev.metrics.ttft * 1000),
            )
            # intentionally not cleared here; on_agent_state_changed still needs eou.timestamp for TTFA

    @session.on("agent_state_changed")
    def on_agent_state_changed(ev: AgentStateChangedEvent) -> None:
        # speech_id guard ensures we pair this EOU with the speech the agent is actually starting,
        # not a leftover from a turn where TTS was cancelled before agent_state_changed fired
        if (
            ev.new_state == "speaking"
            and _last_eou
            and session.current_speech
            and _last_eou[0].speech_id == session.current_speech.id
        ):
            ttfa_ms = (ev.created_at - _last_eou[0].timestamp) * 1000
            log_ttfa(ttfa_ms, _last_eou[0].speech_id)
            _last_eou.clear()

    @session.on("user_state_changed")
    def on_user_state_changed(event) -> None:
        nonlocal _idle_check_sent

        if _forced_end_task is not None:
            return

        if event.new_state == "away" and not _idle_check_sent:
            _idle_check_sent = True
            session.generate_reply(
                instructions="The caller has gone quiet. Ask one short, natural check-in question to re-engage them."
            )
        elif event.new_state == "speaking":
            _idle_check_sent = False

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(ev: UserInputTranscribedEvent) -> None:
        nonlocal _forced_end_task

        if not ev.is_final or _forced_end_task is not None:
            return

        transcript = ev.transcript.strip().lower()
        if transcript and GOODBYE_RE.search(transcript):
            _forced_end_task = asyncio.create_task(
                force_end_call("You're welcome, take care.", reason="caller_goodbye")
            )

    await ctx.connect()         # joins the LiveKit Room (the call's audio channel)

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

        opening_handle = session.generate_reply(instructions=opening_instruction)

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
        # one log line per provider+model combination; zero-value fields are omitted to keep logs lean
        for entry in usage_collector.flatten():
            if entry.type == "llm_usage":
                logger.info(
                    "call.usage.llm",
                    extra={
                        "provider": entry.provider,
                        "model": entry.model,
                        "input_tokens": entry.input_tokens,
                        "cached_tokens": entry.input_cached_tokens,
                        "output_tokens": entry.output_tokens,
                    },
                )
            elif entry.type == "tts_usage":
                logger.info(
                    "call.usage.tts",
                    extra={
                        "provider": entry.provider,
                        "model": entry.model,
                        "characters": entry.characters_count,
                        "audio_duration_s": round(entry.audio_duration, 2),
                    },
                )
            elif entry.type == "stt_usage":
                logger.info(
                    "call.usage.stt",
                    extra={
                        "provider": entry.provider,
                        "model": entry.model,
                        "audio_duration_s": round(entry.audio_duration, 2),
                    },
                )


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
