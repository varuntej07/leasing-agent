import asyncio
import logging
import re

from livekit.agents import (
    AgentSession,
    JobContext,
    AgentStateChangedEvent,
    MetricsCollectedEvent,
    UserInputTranscribedEvent,
)

from src.observability import log_metrics, log_ttfa, log_turn_latency

logger = logging.getLogger(__name__)

_GOODBYE_RE = re.compile(
    r"\b(bye|goodbye|bye[- ]?bye|see you|see ya|talk to you later|that's all|that is all|that's it|that is it|no that's all|no that is all|no that's it|no that is it)\b"
)


class SessionHandler:
    """Owns all per-call session state and wires LiveKit event handlers."""

    def __init__(self, session: AgentSession, ctx: JobContext) -> None:
        self._session = session
        self._ctx = ctx

        # single-element list so the closure can mutate without nonlocal; holds the full EOUMetrics object
        # for the current turn so both log_turn_latency and log_ttfa can read eou.timestamp and eou.speech_id
        self._last_eou: list = []
        self._idle_check_sent: bool = False
        self._forced_end_task: asyncio.Task[None] | None = None

        session.on("metrics_collected", self._on_metrics)
        session.on("agent_state_changed", self._on_agent_state_changed)
        session.on("user_state_changed", self._on_user_state_changed)
        session.on("user_input_transcribed", self._on_user_input_transcribed)

    async def _force_end_call(self, closing_line: str, reason: str) -> None:
        logger.info("call.fast_end.requested", extra={"reason": reason, "transcript_matched": True})
        try:
            handle = self._session.say(closing_line, allow_interruptions=False, add_to_chat_ctx=True)
            await handle.wait_for_playout()
        except Exception:
            logger.exception("call.fast_end.playout_failed", extra={"reason": reason})
        finally:
            try:
                await self._ctx.delete_room()
            except Exception:
                logger.exception("call.fast_end.delete_room_failed", extra={"reason": reason})
            self._session.shutdown(drain=False)
            self._ctx.shutdown(reason=reason)
            self._forced_end_task = None

    def _on_metrics(self, ev: MetricsCollectedEvent) -> None:
        log_metrics(ev.metrics)
        if ev.metrics.type == "eou_metrics":
            # overwrite previous turn's EOU; _on_agent_state_changed clears this after TTFA is logged
            self._last_eou[:] = [ev.metrics]
        elif ev.metrics.type == "llm_metrics" and self._last_eou:
            eou = self._last_eou[0]
            log_turn_latency(
                round(eou.end_of_utterance_delay * 1000),
                round(ev.metrics.ttft * 1000),
            )
            # intentionally not cleared here; _on_agent_state_changed still needs eou.timestamp for TTFA

    def _on_agent_state_changed(self, ev: AgentStateChangedEvent) -> None:
        # speech_id guard ensures we pair this EOU with the speech the agent is actually starting,
        # not a leftover from a turn where TTS was cancelled before agent_state_changed fired
        if (
            ev.new_state == "speaking"
            and self._last_eou
            and self._session.current_speech
            and self._last_eou[0].speech_id == self._session.current_speech.id
        ):
            ttfa_ms = (ev.created_at - self._last_eou[0].timestamp) * 1000
            log_ttfa(ttfa_ms, self._last_eou[0].speech_id)
            self._last_eou.clear()

    def _on_user_state_changed(self, event) -> None:
        if self._forced_end_task is not None:
            return
        if event.new_state == "away" and not self._idle_check_sent:
            self._idle_check_sent = True
            self._session.generate_reply(
                instructions="The caller has gone quiet. Ask one short, natural check-in question to re-engage them."
            )
        elif event.new_state == "speaking":
            self._idle_check_sent = False

    def _on_user_input_transcribed(self, ev: UserInputTranscribedEvent) -> None:
        if not ev.is_final or self._forced_end_task is not None:
            return
        transcript = ev.transcript.strip().lower()
        if transcript and _GOODBYE_RE.search(transcript):
            self._forced_end_task = asyncio.create_task(
                self._force_end_call("You're welcome, take care.", reason="caller_goodbye")
            )

    def flush_usage(self) -> None:
        """Log per-provider usage summaries. Call once at the end of each session."""
        for entry in self._session.usage.model_usage:
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
