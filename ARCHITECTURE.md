# J.A.R.V.I.S. — Architecture Overview

This document outlines the complete architectural design of the J.A.R.V.I.S. voice-controlled AI assistant, encompassing its multi-agent system, voice pipeline, memory systems, and tool execution ecosystem.

---

## 1. High-Level System Flow

The system operates as an ambient, always-on daemon. It listens for a wake word locally, routes the command to a master Orchestrator, selects the appropriate specialized agent, executes tools (plugins), and responds via voice. 

```mermaid
flowchart TD
    User([User Voice]) --> STT[Streaming STT (faster-whisper)]
    STT --> VP[Voice Pipeline State Machine]
    VP --> Orch[Orchestrator]
    
    Orch --> Memory[(Memory & Context)]
    Orch --> Route{Agent Router}
    
    Route --> WA[Web Agent]
    Route --> CA[Coding Agent]
    Route --> AA[Automation Agent]
    Route --> SA[System Agent]
    
    WA -.-> Tools[(Plugin Ecosystem)]
    CA -.-> Tools
    AA -.-> Tools
    SA -.-> Tools
    
    Tools --> VP
    VP --> TTS[Interruptible TTS]
    TTS --> User
```

---

## 2. Core Components

### 2.1 Voice Interface
- **`core/voice_pipeline.py`**: The central state machine (`AMBIENT` → `LISTENING` → `PROCESSING` → `SPEAKING` → `FOLLOW_UP`). It handles conversational turn-taking, interrupting TTS when the wake word is heard again, and ambient continuous listening.
- **`core/streaming_stt.py`**: Runs locally on CPU using `faster-whisper`. Constantly records audio into a buffer, uses VAD (Voice Activity Detection) energy levels to find speech bounds, and emits transcripts. Uses Google Cloud STT as a zero-CPU fallback when online.
- **`core/interruptible_tts.py`**: Uses `edge-tts` to stream human-like synthesized voice directly into `pygame`. Can be hard-interrupted instantly at any time.

### 2.2 Intelligence Engine (LLM)
- **`core/llm_provider.py`**: A hybrid LLM router. It primarily attempts to use **Google Gemini Flash** for extremely fast, high-quality reasoning. If the cloud call fails (e.g., rate limits or no internet), it immediately falls back to a **Local Ollama** instance running `qwen2.5:7b`.
- **`core/planner.py`**: Formats the ReAct prompt, forcing the LLM to output valid JSON tool calls.

### 2.3 Multi-Agent Orchestration
- **`core/orchestrator.py`**: The master meta-agent. It receives a query, splits it into parallel sub-tasks (if necessary), and routes it to the highest-confidence specialized agent.
  - `WebAgent`: Google searching, YouTube playback, browsing.
  - `CodingAgent`: Reading/writing code, running Python scripts, Git, VS Code.
  - `AutomationAgent`: System volume, app launching, terminal, brightness.
  - `SystemAgent`: Catch-all fallback.
- **`ReflectionAgent` (Self-Healing)**: If an agent fails to execute a tool (e.g., invalid parameters), the Orchestrator passes the exact stack trace to the ReflectionAgent, which generates a new plan to fix the error and retries invisibly.

#### Agentic ReAct Brain (`core/agentic_loop.py`)
For open-ended, multi-step goals ("open my email, find the Amazon invoice, then download it"), the Orchestrator routes the command to the **ReAct loop** instead of the single-shot planner. The loop runs a true **Reason → Act → Observe → Re-plan** cycle: it calls a tool, reads the *actual* result, and decides the next action based on what really happened — repeating until the goal is met.
- **Full tool access**: via `core/agentic_tools.py` it can chain *any* of the 127+ registered plugin tools across steps (it reuses the Orchestrator's `ToolManager`, so plugins load once).
- **Routing gate**: `Orchestrator._is_agentic_goal()` is a conservative heuristic — sequencing/conditional phrasing ("then", "until", "for each") or multi-action requests go agentic; simple commands ("open chrome", "set volume to 50") stay on the low-latency single-shot path.
- **Loop safety**: identical repeated tool calls are detected and capped (`MAX_REPEAT`), with one corrective nudge before the workflow ends and synthesizes a spoken summary — so it can never spin forever.
- **Toggle**: set `JARVIS_AGENTIC_MODE=0` to force the classic single-shot pipeline.

### 2.4 Context & Memory
- **`core/memory.py`**: 
  - **Vector Database**: Uses ChromaDB to store past conversational turns and learned facts.
  - **Knowledge Graph**: Extracts triplets (Subject-Predicate-Object) from interactions (e.g., "User's brother is John") for persistent factual recall.
- **`core/vision.py (ScreenMemory)`**: A background daemon that takes compressed screenshots every 5 seconds, maintaining a rolling 6-frame buffer. Allows Jarvis to "see" what's on the screen if you say "what am I looking at?".

### 2.5 Proactive Intelligence & Omnipresence
- **`core/observer.py (ObserverAgent)`**: A background daemon monitoring system telemetry. If CPU or RAM hits critical levels, it will actively seize the Voice Pipeline to issue a proactive warning.
- **`core/telegram_bridge.py`**: Allows remote access. You can text Jarvis on Telegram from your phone, and the commands are routed directly into the Orchestrator as if you spoke them locally.
- **`core/message_bus.py`**: A pub/sub event bus allowing isolated background agents to communicate state changes to one another without circular dependencies.

---

## 3. Plugin / Tool Ecosystem
Located in `plugins/`, dynamically discovered and mapped into OpenAI-compatible JSON schemas by `core/tool_manager.py`.

*Key Plugins:*
- `app_launcher.py`: UWP and Desktop App smart-discovery and launching.
- `messaging.py`: GUI automation for instant WhatsApp messages.
- `computer_use.py`: Mouse/Keyboard visual GUI automation.
- `coding.py`: Local shell, python execution, and file I/O.
- `media_control.py`: Standard media keystrokes (Play/Pause).
- `system_control.py`: Windows-specific APIs (brightness, power, WMI).
- `scheduler.py`: Alarms, timers, and scheduled macros.

---

## 4. UI & Frontend
- **`ui/web_server.py`**: A lightweight `Flask` server combined with `Flask-SocketIO`.
- **`ui/html/index.html`**: A futuristic, responsive dashboard that connects via WebSockets to visualize the voice state (Ambient, Listening, Processing), live transcripts, system health, and an interactive chat log. Replaced the old heavy `CustomTkinter` UI.

---

## 5. Boot Sequence (`main.py`)
1. Checks dependencies and loads environment variables (`.env`).
2. Initializes `ToolManager` and `MemoryManager`.
3. Instantiates `Orchestrator` and `VoicePipeline`.
4. Starts Background Daemons (`PerformanceMonitor`, `VisionAgent`, `ObserverAgent`, `TelegramBridge`).
5. Boots the `Flask` web server and binds the `VoicePipeline` to WebSocket events.
6. A browser window opens to `http://localhost:5000` automatically.
