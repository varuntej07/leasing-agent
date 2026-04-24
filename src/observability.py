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


def log_metrics(event) -> None:
    logger = logging.getLogger("livekit.metrics")
    m = event.metrics
    kind = type(m).__name__

    if kind == "LLMMetrics":
        logger.info(
            "metrics.llm",
            extra={
                "ttft_ms": round(m.ttft * 1000) if getattr(m, "ttft", None) else None,
                "input_tokens": getattr(m, "prompt_tokens", None),
                "output_tokens": getattr(m, "completion_tokens", None),
                "tokens_per_second": getattr(m, "tokens_per_second", None),
                "model": getattr(m, "label", None),
            },
        )
    elif kind == "TTSMetrics":
        logger.info(
            "metrics.tts",
            extra={
                "audio_duration_ms": round(m.audio_duration * 1000) if getattr(m, "audio_duration", None) else None,
                "characters": getattr(m, "characters_count", None),
                "model": getattr(m, "label", None),
            },
        )
    elif kind == "STTMetrics":
        logger.info(
            "metrics.stt",
            extra={
                "audio_duration_ms": round(m.audio_duration * 1000) if getattr(m, "audio_duration", None) else None,
                "model": getattr(m, "label", None),
            },
        )
    elif kind == "EOUMetrics":
        logger.info(
            "metrics.eou",
            extra={
                "eou_delay_ms": round(m.end_of_utterance_delay * 1000) if getattr(m, "end_of_utterance_delay", None) else None,
                "transcription_delay_ms": round(m.transcription_delay * 1000) if getattr(m, "transcription_delay", None) else None,
            },
        )
