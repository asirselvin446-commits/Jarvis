# Enterprise Integration Guide for Jarvis OS

This guide explains how all the enterprise-grade systems work together to create a comprehensive autonomous agent platform.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       Jarvis OS (Enterprise)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐│
│  │  Voice Layer    │  │  Vision Layer    │  │  Execution Layer ││
│  ├─────────────────┤  ├──────────────────┤  ├──────────────────┤│
│  │ • Wake Word     │  │ • Screen Monitor │  │ • Command Parser ││
│  │ • Speech Recog  │  │ • Issue Detect   │  │ • Task Executor  ││
│  │ • VAD           │  │ • Auto-Remediate │  │ • Workflow Build ││
│  │ • Streaming TTS │  │ • Context Learn  │  │ • Safety Check   ││
│  └──────┬──────────┘  └────────┬─────────┘  └────────┬─────────┘│
│         │                      │                      │           │
│         └──────────────────────┼──────────────────────┘           │
│                                │                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │         Orchestration Layer (Core Intelligence)            │  │
│  ├────────────────────────────────────────────────────────────┤  │
│  │ Advanced Orchestrator (Task DAG + Coordination)            │  │
│  │ Dual-Model LLM (Cloud + Local + Fallover)                 │  │
│  │ Voice Orchestrator (Conversation + Interrupts)            │  │
│  │ Enhanced Voice Recognition (Multi-model wake word)        │  │
│  │ Universal Executor (NL → Actions)                         │  │
│  └────────────────────────────────────────────────────────────┘  │
│         │                      │                      │           │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ Memory Layer │  │ Management Layer │  │ Monitoring Layer │   │
│  ├──────────────┤  ├──────────────────┤  ├──────────────────┤   │
│  │ • Semantic   │  │ • System Health  │  │ • Logging        │   │
│  │ • Search     │  │ • Resource Opt   │  │ • Tracing        │   │
│  │ • Learn      │  │ • Maintenance    │  │ • Metrics        │   │
│  │ • Consolidate│  │ • Analytics      │  │ • Alerts         │   │
│  └──────────────┘  └──────────────────┘  └──────────────────┘   │
│         │                      │                      │           │
└─────────│──────────────────────│──────────────────────│───────────┘
          │                      │                      │
          └──────────────────────┴──────────────────────┘
                        ↓
        ┌───────────────────────────────────┐
        │   Persistent Storage Layer        │
        ├───────────────────────────────────┤
        │ • SQLite (Memory, Tasks)          │
        │ • File System (Config, Cache)     │
        │ • Cloud Storage (Optional)        │
        └───────────────────────────────────┘
```

## Core Components

### 1. Voice Orchestrator (`voice_orchestrator.py`)
**Purpose:** Manages real-time voice conversation

**Key Features:**
- Continuous listening with voice activity detection
- Real-time interrupt handling (user can speak anytime)
- Streaming response generation
- Conversation history tracking
- Context-aware responses

**Usage Example:**
```python
from core.voice_orchestrator import get_voice_orchestrator, get_interrupt_handler

# Initialize
orchestrator = get_voice_orchestrator()
orchestrator.start()

# Process user speech
orchestrator.process_audio_input(audio_chunk, transcript)
orchestrator.input_complete()

# Generate response
response = llm.chat(orchestrator.get_conversation_history())
orchestrator.generate_response(response, streaming=True)

# Handle interrupts
interrupt_handler = get_interrupt_handler()
interrupt_handler.start_monitoring()
```

### 2. Enhanced Voice Recognition (`enhanced_voice_recognition.py`)
**Purpose:** Multi-model wake word detection and voice quality assessment

**Key Features:**
- Multiple wake word detection
- Adaptive thresholds learning
- Voice quality assessment
- Environmental context awareness
- User pattern learning

**Usage Example:**
```python
from core.enhanced_voice_recognition import get_voice_recognition_pipeline

pipeline = get_voice_recognition_pipeline()

# Register callback
def on_voice_event(event_type, data):
    print(f"Voice event: {event_type.value}")
    if event_type == VoiceEventType.WAKE_WORD:
        print(f"Detected: {data['wake_word']}")

pipeline.register_callback(on_voice_event)

# Process audio
result = pipeline.process_audio(audio_chunk)
if result["wake_word"]:
    activate_jarvis()
```

### 3. Advanced Orchestrator (`advanced_orchestrator.py`)
**Purpose:** Task DAG execution with dependency management

**Key Features:**
- Topological task ordering
- Parallel task execution
- Circular dependency detection
- Retry policies and fallback chains
- State persistence

**Usage Example:**
```python
from core.advanced_orchestrator import (
    get_advanced_orchestrator, Task, TaskPriority, TaskStatus
)

orchestrator = get_advanced_orchestrator()

# Define tasks
tasks = [
    Task(
        id="research",
        description="Research topic",
        priority=TaskPriority.HIGH,
        timeout=30,
    ),
    Task(
        id="summarize",
        description="Summarize findings",
        depends_on=["research"],
    ),
    Task(
        id="send_email",
        description="Send summary",
        depends_on=["summarize"],
    ),
]

# Execute workflow
result = orchestrator.execute_workflow(
    tasks,
    tool_context={"search_api": search_api},
)
```

### 4. Dual-Model LLM Provider (`dual_model_llm.py`)
**Purpose:** Intelligent switching between cloud and local models

**Key Features:**
- Automatic cloud/local selection
- Intelligent fallover
- Response caching
- Usage metrics and cost tracking
- Query complexity estimation

**Usage Example:**
```python
from core.dual_model_llm import get_dual_model_provider

provider = get_dual_model_provider()

# Chat with automatic model selection
response = provider.chat(
    messages=[
        {"role": "user", "content": "What's the weather?"},
    ],
    model_type=ModelType.AUTO,  # Auto-selects best model
)

# Check metrics
print(provider.get_metrics())
# Output: {
#   "cloud_calls": 15,
#   "local_calls": 42,
#   "cached_calls": 8,
#   "cache_hit_rate": 12.5,
#   "avg_latency_ms": 245.3,
# }
```

### 5. Screen Diagnostics (`screen_diagnostics.py`)
**Purpose:** Monitor screen for issues and auto-remediate

**Key Features:**
- Real-time error detection
- Visual issue analysis
- System resource monitoring
- Auto-remediation suggestions
- Issue history tracking

**Usage Example:**
```python
from core.screen_diagnostics import get_screen_diagnostics

diagnostics = get_screen_diagnostics()
diagnostics.start_monitoring()

def on_issue_detected(issue):
    print(f"Issue: {issue.title}")
    print(f"Severity: {issue.severity}")
    if issue.can_auto_fix:
        diagnostics.apply_fix(issue)

diagnostics.on_issue_detected = on_issue_detected
```

### 6. Universal Executor (`universal_executor.py`)
**Purpose:** Convert natural language to executable actions

**Key Features:**
- NL command parsing
- Risk assessment
- Safe execution with confirmation
- Retry and fallback
- Execution history

**Usage Example:**
```python
from core.universal_executor import get_command_executor, ExecutionRisk

executor = get_command_executor()

# Register custom command
def send_email_handler(params, context):
    return f"Email sent to {params['recipient']}"

executor.register_command(
    "send_email",
    "Send an email to someone",
    handler=send_email_handler,
    risk_level=ExecutionRisk.LOW,
    parameters=[
        {"name": "recipient", "pattern": r"to\s+(\S+)"},
        {"name": "subject", "pattern": r"subject:\s+(.+?)(?:\n|$)"},
    ],
)

# Execute natural language command
result = executor.execute("Send email to john@example.com subject: Meeting")
# Result: {"success": True, "output": "Email sent to john@example.com"}
```

### 7. System Manager (`system_manager.py`)
**Purpose:** Monitor and optimize system resources

**Key Features:**
- Real-time system metrics
- Health status tracking
- Automatic optimization
- Maintenance recommendations
- Performance analytics

**Usage Example:**
```python
from core.system_manager import get_system_manager, SystemHealth

manager = get_system_manager()
manager.start_monitoring()

def on_health_change(new_health, score):
    print(f"Health changed to {new_health.value}")
    if new_health == SystemHealth.CRITICAL:
        # Take action
        manager.auto_optimize = True

manager.on_health_change = on_health_change

# Get report
report = manager.export_report()
```

## Integration Workflow: "Order Anything"

Here's how a user's voice command flows through the entire system:

```
1. USER: "Hey Jarvis, order 10 pizzas for lunch"
   │
   ├─→ [Wake Word Detection] ──→ Enhanced Voice Recognition
   │   Detects "Hey Jarvis", activates system
   │
2. [Voice Activity Detection] ──→ Voice Orchestrator
   │   Records: "order 10 pizzas for lunch"
   │   Confidence: 0.95
   │
3. [Speech Recognition] ──→ Voice Orchestrator.input_complete()
   │   user_input_buffer = "order 10 pizzas for lunch"
   │
4. [LLM Processing] ──→ Dual-Model LLM Provider
   │   History: [{"role": "user", "content": "order 10 pizzas for lunch"}]
   │   Selects: LOCAL (simple command, low latency)
   │   Response: "I'll help you order pizzas. How many toppings?"
   │
5. [Command Parsing] ──→ Universal Executor
   │   Parsed: Command("order", params={"item": "pizzas", "quantity": 10})
   │   Risk Level: MEDIUM (requires payment)
   │   Status: REQUIRES_CONFIRMATION
   │
6. [Voice Response] ──→ Voice Orchestrator
   │   Streams: "I'll help you order 10 pizzas..."
   │   Monitors for: User interrupts
   │
7. [User Confirmation] ──→ Voice Processing
   │   User says: "Yes, go ahead"
   │   Interrupt detected: False (we completed streaming)
   │
8. [Execution] ──→ Universal Executor.confirm_and_execute()
   │   Executes: Pizza ordering API call
   │   Result: Order #12345 confirmed
   │   Stored in History
   │
9. [Response Generation] ──→ Dual-Model LLM
   │   Generates: "Order #12345 is confirmed. 30 minutes delivery."
   │
10. [Voice Output] ──→ Voice Orchestrator
    │    Streams response with TTS
    │    Ready for next command
    │
11. [Health Check] ──→ System Manager
    │    Metrics OK
    │    No optimization needed
    │
12. [Screen Monitor] ──→ Screen Diagnostics
    │    No issues detected
    │    Everything normal
```

## Configuration

### Environment Variables

```bash
# Cloud LLM
export GOOGLE_API_KEY="your-gemini-api-key"

# Local LLM
export OLLAMA_URL="http://localhost:11434"

# Voice
export MICROPHONE_DEVICE="default"
export SPEAKER_DEVICE="default"

# System
export JARVIS_DATA_DIR="~/.jarvis"
export JARVIS_LOG_LEVEL="INFO"
```

### Command Registry Setup

```python
def setup_command_registry(executor):
    """Initialize command registry for all common actions."""
    
    # Web commands
    executor.register_command(
        "web_search",
        "Search the web for information",
        handler=web_search_handler,
        risk_level=ExecutionRisk.SAFE,
    )
    
    # Email commands
    executor.register_command(
        "send_email",
        "Send an email",
        handler=email_handler,
        risk_level=ExecutionRisk.LOW,
        requires_confirmation=True,
    )
    
    # System commands
    executor.register_command(
        "shutdown",
        "Shut down the system",
        handler=shutdown_handler,
        risk_level=ExecutionRisk.CRITICAL,
        requires_confirmation=True,
    )
    
    # ... many more
```

## Phase 1 Completion Checklist

- [x] Advanced Orchestrator (Task DAG + Error Handling)
- [x] Screen Diagnostics (Issue Detection + Auto-Remediation)
- [x] Dual-Model LLM Provider (Cloud + Local + Fallover)
- [x] Enhanced Voice Recognition (Multi-model wake word)
- [x] Voice Orchestrator (Seamless conversation)
- [x] Universal Executor (NL → Actions)
- [x] System Manager (Health + Optimization)

## What's Enabled Now

### ✅ Agentic Workflows
- Task DAG with dependency management
- Parallel execution with error recovery
- State persistence and resumption

### ✅ Universal Command Execution
- Natural language command parsing
- Multi-step workflows
- Safety-aware execution with confirmation

### ✅ Screen Monitoring
- Real-time error detection
- Visual issue analysis
- Automated remediation suggestions

### ✅ Cloud + Local LLM
- Intelligent model selection
- Automatic fallover
- Cost optimization

### ✅ Seamless Voice
- Continuous listening
- Real-time interrupt handling
- Streaming responses

### ✅ System Management
- Real-time health monitoring
- Automatic resource optimization
- Proactive maintenance

### ✅ Enhanced Voice Recognition
- Multi-model wake word detection
- Adaptive thresholds
- User learning

## Next Steps: Phase 2

1. **Integration Testing**
   - Test full workflow: Voice → Orchestrator → Executor → Response
   - Test interrupt handling during task execution
   - Test fallover between cloud and local LLM

2. **Production Hardening**
   - Add persistent state management for long-running tasks
   - Implement session recovery
   - Add comprehensive error handling

3. **Advanced Features**
   - Multi-user support with isolation
   - Custom plugin development
   - Advanced analytics dashboard

4. **Performance Optimization**
   - Profile and optimize bottlenecks
   - Implement caching strategies
   - Optimize memory usage

## Documentation

Each system includes comprehensive docstrings and logging. To understand any component:

1. Read the class docstring
2. Review the `__init__` method
3. Check the public methods
4. Review example usage in this guide

## Support & Troubleshooting

### High CPU Usage
- Check `system_manager.get_health_status()`
- Review `system_manager.get_top_processes()`
- Check background tasks in orchestrator

### Voice Not Detecting
- Check `voice_recognition_pipeline.get_statistics()`
- Verify microphone device
- Adjust sensitivity thresholds

### LLM Slow Responses
- Check `dual_model_llm.get_metrics()`
- Monitor network connectivity
- Check local Ollama status

### Task Execution Failing
- Review `advanced_orchestrator.get_task_status()`
- Check error handling in task definition
- Verify dependencies are met
