# AI Leasing Agent

A voice AI agent that handles apartment leasing calls end-to-end over the phone eliminating human requirement for the common case.

Prospective tenants call in, speak naturally, and the agent checks real-time unit availability, answers property questions (amenities, pet policy, parking, lease terms), and books tour appointments — all within a single phone call. A separate outbound agent calls prospects to confirm, reschedule, or cancel upcoming tours.

The agent manages three Seattle-area properties: Cascade Heights (Bellevue), The Meridian (Redmond), and Pineview Commons (Kirkland).

## Stack

- **Orchestration**: LiveKit Agents v1.x — handles the full STT -> LLM -> TTS pipeline, VAD, turn detection, and SIP telephony
- **STT**: Deepgram Nova-3 — low-latency, phone-quality transcription
- **LLM**: GPT-4.1-mini — tool-calling for availability checks and scheduling
- **TTS**: Cartesia Sonic-2 — natural-sounding voice output
- **VAD**: Silero — filters silence and background noise before sending audio to STT
- **Observability**: structured JSON logs (python-json-logger) with per-tool timing and LiveKit pipeline metrics

## Setup

```bash
pip install -r requirements.txt
python -m src.main download-files
```

`download-files` fetches the multilingual turn-detector ONNX model required at runtime. Fill in `.env` with your LiveKit, Deepgram, OpenAI, and Cartesia API keys.

## Run

```bash
python -m src.main dev
```

Starts the LiveKit worker. Connect via the [LiveKit Agents Playground](https://agents-playground.livekit.io/) to test without a phone, or call the configured SIP number directly.
