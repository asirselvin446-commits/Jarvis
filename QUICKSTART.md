# Quick Start: Advanced Features for Jarvis OS

## 🚀 5-Minute Setup

### Step 1: Initialize the Systems

Add this to your `main.py` or `agent.py`:

```python
# Initialize advanced systems on startup
from core.advanced_integration import get_integration

integration = get_integration()
print("✓ Advanced features loaded")
print(f"✓ Available tools: {len(integration.get_available_tools())}")
print(f"✓ Plugins loaded: {len(integration.list_plugins())}")
```

### Step 2: Use in Your Agent Loop

```python
# Before processing user command
integration = get_integration()
context = integration.get_agent_context()

# Remember what user asked
integration.remember(
    content=f"User asked: {user_input}",
    memory_type="conversation"
)

# Analyze screen before responding
screen = integration.analyze_screen()
if screen["error_detected"]:
    # Handle error
    error_msg = screen["error_message"]
    print(f"⚠️ Error detected: {error_msg}")

# Execute tools from plugins
result = integration.execute_tool("web_search", query="...")

# Recall relevant memories
memories = integration.recall(query=user_input, limit=3)
```

---

## 🔌 Quick Plugin Creation

### Option 1: Simple Python Plugin

Create `plugins/my_plugin/my_plugin.py`:

```python
from core.tool_manager import tool

class MyPlugin:
    def __init__(self, config=None):
        self.config = config or {}

@tool(
    name="my_tool",
    description="Does something useful",
    parameters={
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Input text"}
        }
    }
)
def my_tool(input: str) -> str:
    return f"Processed: {input}"
```

### Option 2: Create Plugin Manifest

Create `plugins/my_plugin/plugin.json`:

```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "My custom plugin",
  "author": "Your Name",
  "entry_point": "my_plugin:MyPlugin",
  "dependencies": [],
  "enabled": true
}
```

### Option 3: Load the Plugin

```python
integration.load_plugin("my_plugin")
integration.execute_tool("my_tool", input="hello")
```

---

## 💾 Using Memory

### Store Memories

```python
integration.remember(
    content="User prefers dark mode",
    memory_type="preference",
    tags=["ui", "accessibility"]
)
```

### Recall Memories

```python
# Search for relevant memories
memories = integration.recall(
    query="dark mode",
    memory_type="preference",
    limit=5
)

for memory in memories:
    print(f"📝 {memory['content']}")
```

### Link Related Memories

```python
integration.link_memories(
    from_id="memory_1",
    to_id="memory_2",
    relationship="related_to"
)
```

### Get Memory Stats

```python
stats = integration.get_memory_stats()
print(f"Total memories: {stats['total_memories']}")
print(f"By type: {stats['by_type']}")
```

---

## 👁️ Vision System

### Analyze Current Screen

```python
analysis = integration.analyze_screen()

print(f"Text on screen: {analysis['raw_text'][:100]}...")
print(f"Description: {analysis['description']}")
print(f"Error? {analysis['error_detected']}")
print(f"UI Elements: {len(analysis['ui_elements'])}")
```

### Get Just Text (OCR)

```python
text = integration.read_screen()
print(f"Screen text: {text}")
```

### Find Clickable Elements

```python
elements = integration.detect_ui_elements()
for element in elements:
    if element["interactive"]:
        print(f"Button: {element['label']} at {element['position']}")
```

### Detect Errors

```python
error = integration.detect_errors()
if error:
    print(f"❌ Error found: {error}")
```

---

## 🎯 Common Patterns

### Pattern 1: Context-Aware Response

```python
# Get full context
context = integration.get_agent_context()

# Use in LLM prompt
prompt = f"""
Recent memories: {context['recent_memories']}
Screen state: {context['screen_analysis']['description']}
Available actions: {context['available_tools']}

User asked: {user_query}
"""
```

### Pattern 2: Learning from User Actions

```python
# After user does something
integration.remember(
    content=f"User executed: {action}",
    memory_type="workflow",
    tags=[action, "user_action"],
    metadata={
        "timestamp": datetime.now().isoformat(),
        "context": current_context
    }
)
```

### Pattern 3: Error Recovery

```python
error = integration.detect_errors()
if error:
    # Search for similar past errors
    past_errors = integration.recall(
        query=error,
        memory_type="error"
    )
    
    if past_errors:
        # Found solution from past
        solution = past_errors[0]
        print(f"Solution: {solution}")
    else:
        # Learn this new error
        integration.remember(
            content=error,
            memory_type="error",
            tags=["error", "solution_pending"]
        )
```

### Pattern 4: Tool Discovery & Execution

```python
# Get all available tools
tools = integration.get_available_tools()

# Filter tools by name pattern
search_tools = [t for t in tools.keys() if "search" in t]

# Execute appropriate tool
if search_tools:
    result = integration.execute_tool(
        search_tools[0],
        query=user_query
    )
```

---

## 📊 Monitoring

### Check System Status

```python
# Plugin status
for plugin in integration.list_plugins():
    print(f"{plugin['name']}: {plugin['status']}")

# Memory usage
stats = integration.get_memory_stats()
print(f"Memories: {stats['total_memories']}")
print(f"Cache size: {stats['cache_size']}")

# Tool cache
tools = integration.get_available_tools()
print(f"Available tools: {len(tools)}")
```

### Debug Plugin Issues

```python
from core.plugin_loader import get_plugin_registry
registry = get_plugin_registry()

status = registry.get_plugin_status("problem_plugin")
print(f"Status: {status}")

# Reload if needed
registry.reload_plugin("problem_plugin")
```

---

## ⚙️ Configuration

### Plugin Config File

Save to `~/.jarvis/plugins/my_plugin.json`:

```json
{
  "enabled": true,
  "timeout": 30,
  "api_key": "sk-...",
  "custom_setting": "value"
}
```

### Load in Plugin

```python
class MyPlugin:
    def __init__(self, config=None):
        self.config = config or {}
        self.timeout = self.config.get("timeout", 30)
        self.api_key = self.config.get("api_key")
```

---

## 🔍 Troubleshooting

### Plugin Won't Load

```python
from core.plugin_loader import get_plugin_registry
import logging

logging.basicConfig(level=logging.DEBUG)
registry = get_plugin_registry()

if not registry.load_plugin("my_plugin"):
    status = registry.get_plugin_status("my_plugin")
    print(f"Plugin status: {status}")
```

### Memory Search Not Working

```python
# Check if memories exist
stats = get_memory_manager().get_memory_stats()
print(f"Total memories: {stats['total_memories']}")

# Try with lower relevance threshold
results = integration.recall(query="...", limit=1)
```

### Vision Analysis Failing

```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Check model is installed
ollama list

# Restart Ollama if needed
ollama serve
```

---

## 📚 Full Documentation

- **ADVANCED_FEATURES_GUIDE.md** - Complete reference
- **IMPROVEMENTS_SUMMARY.md** - What was added and why
- **plugins/semantic_analyzer.py** - Example plugin

---

## 🎓 Example Use Cases

### Use Case 1: Smart Error Handler
```python
error = integration.detect_errors()
if error:
    # Search memory for this error type
    solutions = integration.recall(error, memory_type="error", limit=1)
    
    if solutions:
        # Apply known solution
        apply_solution(solutions[0])
    else:
        # Learn new error
        integration.remember(error, memory_type="error")
```

### Use Case 2: Personalized Assistant
```python
# Recall user preferences
prefs = integration.recall("preferences", limit=5)

# Remember new preference
integration.remember(
    "User likes concise responses",
    memory_type="preference"
)

# Use in LLM system prompt
system_prompt = build_prompt(prefs)
```

### Use Case 3: Workflow Automation
```python
# Analyze screen to understand current state
screen = integration.analyze_screen()

# Search for similar past workflows
workflows = integration.recall(
    screen["description"],
    memory_type="workflow"
)

# Execute most relevant workflow
if workflows:
    execute_workflow(workflows[0])
```

---

## ✅ Checklist for Integration

- [ ] Add `get_integration()` call to main agent
- [ ] Enable memory storing for key events
- [ ] Use vision analysis before state-changing actions
- [ ] Create your first custom plugin
- [ ] Configure plugin settings
- [ ] Test tool execution
- [ ] Monitor memory growth
- [ ] Review logs for errors

---

## 🚀 Next: Make It Your Own

1. **Customize plugins** - Create domain-specific tools
2. **Fine-tune memory** - Adjust what gets remembered
3. **Optimize vision** - Train on your specific apps
4. **Expand integration** - Add more context sources

Happy building! 🎉
