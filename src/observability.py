import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar

from pythonjsonlogger.json import JsonFormatter as _JsonFormatter

_session_id: ContextVar[str] = ContextVar("session_id", default="")


class _SessionFilter(logging.Filter):
    """Injects the current session_id into every log record."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = _session_id.get("")
        return True


def bind_session(session_id: str) -> None:
    """Call once per entrypoint to stamp all subsequent logs with the room name."""
    _session_id.set(session_id)


def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        _JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler.addFilter(_SessionFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


@asynccontextmanager
async def tool_span(logger: logging.Logger, tool_name: str, **ctx):
    t0 = time.perf_counter()
    logger.info("tool.called", extra={"tool": tool_name, **ctx})
    try:
        yield
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info("tool.ok", extra={"tool": tool_name, "duration_ms": elapsed, **ctx})
    except asyncio.TimeoutError:
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.error("tool.timeout", extra={"tool": tool_name, "duration_ms": elapsed, **ctx})
        raise
    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.error(
            "tool.error",
            extra={"tool": tool_name, "error": str(exc), "duration_ms": elapsed, **ctx},
        )
        raise


def log_turn_latency(eou_delay_ms: int, ttft_ms: int) -> None:
    # eou_plus_llm_ms is the LLM pipeline cost only; metrics.ttfa captures the full pipeline to first audio
    logging.getLogger("livekit.metrics").info(
        "metrics.turn",
        extra={
            "eou_delay_ms": eou_delay_ms,
            "ttft_ms": ttft_ms,
            "eou_plus_llm_ms": eou_delay_ms + ttft_ms,
        },
    )


def log_ttfa(ttfa_ms: float, speech_id: str | None) -> None:
    # measured from EOU decision timestamp to agent_state_changed("speaking"); spans LLM inference and TTS startup
    logging.getLogger("livekit.metrics").info(
        "metrics.ttfa",
        extra={
            "ttfa_ms": round(ttfa_ms),
            "speech_id": speech_id,
        },
    )


def log_metrics(m) -> None:
    logger = logging.getLogger("livekit.metrics")

    # m.type is a string literal field on each metrics dataclass; using it avoids accidentally
    # matching against MetricsCollectedEvent (the wrapper) instead of the inner object
    if m.type == "llm_metrics":
        logger.info(
            "metrics.llm",
            extra={
                "ttft_ms": round(m.ttft * 1000),
                "input_tokens": m.prompt_tokens,
                "cached_tokens": m.prompt_cached_tokens,
                "output_tokens": m.completion_tokens,
                "tokens_per_second": round(m.tokens_per_second, 1),
                "model": m.label,
            },
        )
    elif m.type == "tts_metrics":
        logger.info(
            "metrics.tts",
            extra={
                "ttfb_ms": round(m.ttfb * 1000),
                "audio_duration_ms": round(m.audio_duration * 1000),
                "characters": m.characters_count,
                "model": m.label,
            },
        )
    elif m.type == "stt_metrics":
        logger.info(
            "metrics.stt",
            extra={
                "audio_duration_ms": round(m.audio_duration * 1000),
                "model": m.label,
            },
        )
    elif m.type == "eou_metrics":
        logger.info(
            "metrics.eou",
            extra={
                "eou_delay_ms": round(m.end_of_utterance_delay * 1000),
                "transcription_delay_ms": round(m.transcription_delay * 1000),
            },
        )
