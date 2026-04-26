Repository guidance for Claude Code and other coding agents working in this project.

## Core Commands

Download model files: `python -m src.main download-files`

Run the worker locally: `python -m src.main dev`

Test without a phone in the LiveKit Agents Playground: https://agents-playground.livekit.io/

Required `.env` keys for successfully running the agent:

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `DEEPGRAM_API_KEY`
- `OPENAI_API_KEY`
- `CARTESIA_API_KEY`

## Architecture Invariants

### Call Routing

- `src/main.py` always starts `InboundLeasingAgent`. The worker is inbound-only.

### Agent Structure

- `LeasingAgent` owns shared behavior and common tools.
- `InboundLeasingAgent` adds leasing-specific tools:
  - `check_availability`
  - `schedule_tour`
  - `get_property_info`
  - `submit_maintenance_request`
- `session.py` holds per-call state and is bound to each room via `bind_session(ctx.room.name)`.

### Tool Calling Design

- Implementations live in `src/tools/`.
- Tool functions should stay thin and deterministic.
- Tool-facing agent methods use `@function_tool`.
- Tool docstrings are part of the model interface. LiveKit turns them into tool descriptions, so do not casually weaken or remove them.

### Data Layer

Persistence is flat JSON under `src/data/` for POC:

- `units.json`
- `properties.json`
- `tours.json`
- `maintenance_requests.json`

Canonical property IDs used in the data files for POC:

- `cascade-heights`
- `the-meridian`
- `pineview-commons`

## Observability Rules

- `setup_logging()` must run once at process startup.
- `bind_session(ctx.room.name)` must be called per session so logs stay attributable to a room.
- Every tool should be wrapped in `async with tool_span(logger, "tool_name", ...)`.
- LLM, STT, TTS, and end-of-utterance metrics are logged from the LiveKit cloud using the session event handlers in `src/main.py`.


## Workflow Style

### Planning

- Enter plan mode for any non-trivial task (2+ steps) to get user approval for the plan.
- If something goes sideways, STOP and re-plan immediately.

### Execution

- ALWAYS ask clarifying questions when you are not 100% sure of what to do.
- Use subagents for research, exploration, and parallel analysis.
- Track progress in tasks; mark items complete as you go.
- Write a high-level summary after each task is completed in plain English.

### Bug Fixes

- When given a bug report, find the root cause and justify your reasoning for why and propose plan of action and what changes make the bug fix.
- Get approval from the user before making changes.
- If needed, point at logs, errors, or failing tests, then resolve them.

### Guardrails

- Always fetch the latest documentation for specific packages, tools, or SDKs you are working with.
- If a bug persists after multiple attempts to fix, consult documentation and get user approval before making a decision.
- DO NOT git add, git commit, or git push any changes unless explicitly asked by the user.
