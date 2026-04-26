# AI Leasing Agent

A voice AI leasing and resident-support agent built with LiveKit Agents.

The agent handles inbound calls for three Seattle-area apartment communities. Callers can ask about availability, book tours, request property information, and submit maintenance requests in a single conversation.

Managed properties (dummy data for POC):

- `cascade-heights` - Bellevue, WA
- `the-meridian` - Redmond, WA
- `pineview-commons` - Kirkland, WA

## What It Does

- Answers inbound leasing and resident-support calls over voice
- Checks apartment availability from structured inventory data
- Books tours and returns confirmation IDs
- Answers property-specific questions by category
- Collects and logs maintenance requests
- Transfers callers to a human when requested

## Stack

- Orchestration: LiveKit Agents v1
- STT: Deepgram Nova-3 with Nova-2 fallback
- LLM: GPT-4o-mini with GPT-4o fallback
- TTS: Cartesia Sonic-2 with Sonic-1 fallback
- VAD: Silero
- Turn detection: LiveKit MultilingualModel
- Data store: local JSON files in `src/data/`
- Observability: LiveKit Cloud Insights for traces, transcripts, recordings, and latency, plus structured JSON worker  logs for tool timing and model-usage details  

## Repository Layout

```text
src/
  agents/
    base.py           # Shared LeasingAgent with transfer_to_human tool
    inbound.py        # InboundLeasingAgent with leasing and maintenance tools
    prompts.py        # System prompt templates
  data/
    units.json               # Apartment unit inventory
    properties.json          # Property details and FAQs
    tours.json               # Scheduled tour records
    maintenance_requests.json   # Submitted maintenance requests
  tools/
    availability.py   # check_availability implementation
    scheduling.py     # schedule_tour implementation
    property_info.py  # get_property_info implementation
    maintenance.py    # submit_maintenance_request implementation
    transfer.py       # transfer_to_human implementation
  main.py             # LiveKit worker entrypoint
  session.py          # Session context and per-call state
  observability.py    # Structured logging and metrics helpers
scripts/
  setup_dispatch_rule.py
```

## Setup

1. Install dependencies.

```bash
pip install -r requirements.txt
```

2. Create a `.env` file with:

```text
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
DEEPGRAM_API_KEY=
OPENAI_API_KEY=
CARTESIA_API_KEY=
```

3. Download the turn-detector model required by LiveKit.

```bash
python -m src.main download-files
```

## Run

Start the worker:

```bash
python -m src.main dev
```

Test without a phone number using LiveKit Agents Playground: https://agents-playground.livekit.io/

You can also connect the worker to SIP and call it through your configured phone number.

## Architecture Summary

- `entrypoint()` in `src/main.py` starts an `InboundLeasingAgent` for each call.
- `LeasingAgent` provides shared tools such as `transfer_to_human`.
- `InboundLeasingAgent` adds the leasing-specific tools:
  - `check_availability`
  - `get_property_info`
  - `schedule_tour`
  - `submit_maintenance_request`
- Tool implementations are intentionally thin and operate on local JSON data.

## Observability

The worker emits structured logs to stdout. Current coverage includes:

- LLM metrics: token counts, cached tokens, output tokens, tokens per second
- TTS metrics: characters, time to first byte, audio duration
- STT metrics: audio duration
- End-of-utterance metrics: endpointing and transcription delay
- Per-tool timing: `tool.called`, `tool.ok`, `tool.timeout`, `tool.error`
- Per-call usage summaries: `call.usage.llm`, `call.usage.tts`, `call.usage.stt`

Example PowerShell filter for usage logs:

```powershell
python -m src.main dev | Select-String "metrics.llm|call.usage.llm|call.usage.tts|call.usage.stt"
```

## Evaluation Approach

This repo is instrumented to support practical voice-agent evaluation:

- Task completion: successful tour bookings, maintenance submissions, and property information lookups.
- Behavioral compliance: whether the agent follows tool use and prompt rules
- Latency: turn-level timing and end-to-end responsiveness
- STT quality: correctness on property names, unit IDs, and phone numbers

The current implementation is designed as a take-home project (POC) with local data files rather than a production deployment.

## Notes

- `@function_tool` docstrings matter. LiveKit turns them into tool descriptions shown to the model.
- The worker is inbound-only.
- Persistence is file-backed and intended for demonstration, not multi-worker production use.
- I tested the agent (after running the script) by calling 2042122069, a phone number I purchased through LiveKit.

## Context

This project was built as a technical assessment for the AI Engineer role at [Hiya](https://hiya.com).
