# J.A.R.V.I.S Advanced Features Implementation Guide

## Overview

This guide explains the three major feature additions to the Jarvis OS system:

1. **Advanced Plugin System** - Dynamic plugin loading with dependency resolution
2. **Enhanced Memory System** - Semantic search, memory consolidation, and context management
3. **Advanced Vision System** - Object detection, UI understanding, and screen analysis

---

## 1. Advanced Plugin System (`core/plugin_loader.py`)

### Purpose
Enables modular, extensible architecture where plugins can be:
- Dynamically loaded/unloaded at runtime
- Configured via JSON
- Managed with dependency resolution
- Registered and discovered automatically

### Key Classes

#### `PluginMetadata`
- Stores plugin configuration
- Loaded from `plugin.json` in each plugin directory
- Tracks version, dependencies, and configuration schema

#### `PluginRegistry`
- Central hub for plugin management
- Scans `plugins/` directory for `plugin.json` files
- Loads plugins with dependency resolution
- Extracts tools from loaded plugins

### Usage in Your Code

```python
from core.plugin_loader import get_plugin_registry

# Get the global registry
registry = get_plugin_registry()

# List all plugins
plugins = registry.list_plugins()
print(f"Available plugins: {[p['name'] for p in plugins]}")

# Load a plugin
registry.load_plugin("web_browser", config={"timeout": 30})

# Get all tools from loaded plugins
all_tools = registry.get_all_tools()

# Unload a plugin
registry.unload_plugin("web_browser")
```

### Creating a New Plugin

1. Create a new directory in `plugins/`:
   ```
   plugins/my_plugin/
   ├── plugin.json
   └── my_plugin.py
   ```

2. Create `plugins/my_plugin/plugin.json`:
   ```json
   {
     "name": "my_plugin",
     "version": "1.0.0",
     "description": "My custom plugin",
     "author": "Your Name",
     "entry_point": "my_plugin:MyPlugin",
     "dependencies": ["web_browser"],
     "enabled": true
   }
   ```

3. Create `plugins/my_plugin/my_plugin.py`:
   ```python
   from core.tool_manager import tool
   
   class MyPlugin:
       def __init__(self, config=None):
           self.config = config or {}
       
       def cleanup(self):
           """Called when plugin is unloaded"""
           pass
   
   # Define tools that the agent can call
   @tool(
       name="my_tool",
       description="Does something useful",
       parameters={...}
   )
   def my_tool_function(arg1: str) -> str:
       return f"Result: {arg1}"
   ```

---

## 2. Enhanced Memory System (`core/advanced_memory.py`)

### Purpose
Provides advanced memory capabilities:
- Multiple memory types (conversation, preference, skill, error, workflow)
- Semantic search with relevance scoring
- Knowledge graph relationships between memories
- Automatic memory consolidation
- Access statistics for relevance decay

### Key Classes

#### `MemoryType` (Enum)
- CONVERSATION - Past conversations
- CONTEXT - Current context
- PREFERENCE - User preferences
- SKILL - Learned skills/patterns
- ERROR - Error patterns and solutions
- WORKFLOW - Common workflows
- RELATIONSHIP - Entity relationships
- EVENT - Important events

#### `MemoryEntry`
- Represents a single memory with metadata
- Tracks creation time, access count, relevance score
- Supports tags and custom metadata

#### `EnhancedMemoryManager`
- Handles all memory operations
- Uses SQLite for structured data
- Supports complex queries with filtering
- Implements access-based relevance decay

### Usage in Your Code

```python
from core.advanced_memory import get_memory_manager, MemoryType

memory = get_memory_manager()

# Store a memory
entry = memory.store_memory(
    content="User prefers dark mode",
    memory_type=MemoryType.PREFERENCE,
    tags=["ui", "preferences"],
    metadata={"importance": "high"}
)

# Search for memories
results = memory.search_memories(
    query="dark mode",
    memory_type=MemoryType.PREFERENCE,
    limit=5
)

# Get recent context
context = memory.get_context_memories(num_recent=3)

# Link related memories (knowledge graph)
memory.link_memories(entry1.id, entry2.id, "related_to")

# Consolidate old memories
consolidated = memory.consolidate_memories(
    [old_entry1.id, old_entry2.id],
    reason="automatic_consolidation"
)

# Get memory statistics
stats = memory.get_memory_stats()
print(f"Total memories: {stats['total_memories']}")
```

### Database Schema

```sql
-- Main memory storage
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    content TEXT,
    memory_type TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    relevance_score REAL,
    tags TEXT (JSON),
    metadata TEXT (JSON),
    access_count INTEGER,
    last_accessed DATETIME
)

-- Knowledge graph relationships
CREATE TABLE memory_relationships (
    from_id TEXT,
    to_id TEXT,
    relationship_type TEXT,
    confidence REAL
)

-- Consolidation history
CREATE TABLE consolidation_log (
    source_ids TEXT (JSON),
    target_id TEXT,
    consolidated_at DATETIME,
    reason TEXT
)
```

---

## 3. Advanced Vision System (`core/advanced_vision.py`)

### Purpose
Provides comprehensive screen understanding:
- Text extraction (OCR)
- UI element detection and classification
- Error detection and diagnosis
- Screen layout analysis
- Application change detection

### Key Classes

#### `UIElementType` (Enum)
- BUTTON, INPUT_FIELD, CHECKBOX, DROPDOWN
- MENU, DIALOG, NOTIFICATION, ERROR
- TEXT, IMAGE, TABLE, LINK, UNKNOWN

#### `UIElement`
- Represents a detected UI element
- Stores position, size, confidence, interactivity
- Includes text content and semantic type

#### `ScreenAnalysis`
- Complete analysis result
- Includes raw text, description, UI elements
- Detects errors and provides suggestions

#### `AdvancedVisionSystem`
- Main vision interface
- Captures screen as base64 JPEG
- Calls Ollama vision model for analysis
- Maintains analysis history

### Usage in Your Code

```python
from core.advanced_vision import get_vision_system

vision = get_vision_system()

# Comprehensive screen analysis
analysis = vision.analyze_screen_comprehensive()
print(f"Text: {analysis.raw_text}")
print(f"Description: {analysis.description}")
print(f"Error detected: {analysis.error_detected}")
print(f"UI Elements: {len(analysis.ui_elements)}")

# Get just the text
text = vision._analyze_screen_text(b64_image)

# Detect errors
error_info = vision._detect_errors(b64_image)
if error_info["detected"]:
    print(f"Error: {error_info['message']}")

# Find clickable elements
clickables = vision.get_clickable_elements()

# Detect app changes
changes = vision.detect_app_changes()
if changes["changed"]:
    print("Application or UI has changed")

# Find element at position
element = vision.get_element_at_position(x=500, y=300)

# Export analysis as JSON
json_export = vision.export_analysis()
```

### Vision Model Requirements

The system uses Ollama with the Qwen2.5-VL 3B model:

```bash
# Install/run Ollama
ollama pull qwen2.5vl:3b
ollama serve

# Or set custom URL
export OLLAMA_URL="http://your-server:11434"
```

---

## 4. Integration Layer (`core/advanced_integration.py`)

### Purpose
Bridges all systems with a unified interface for the main agent:
- Single point of access for plugins, memory, and vision
- Automatic tool discovery and caching
- Centralized context management
- Unified logging and error handling

### Key Class

#### `AdvancedFeaturesIntegration`
- Initializes all systems
- Provides unified API
- Auto-loads enabled plugins
- Caches tools for fast access

### Usage in Your Code

```python
from core.advanced_integration import get_integration

integration = get_integration()

# ─── Plugin Management ────────────────────────
tools = integration.get_available_tools()
result = integration.execute_tool("web_search", query="Python async")

integration.load_plugin("custom_plugin")
integration.reload_plugin("web_browser")

# ─── Memory Operations ───────────────────────
memory_id = integration.remember(
    content="User likes efficient workflows",
    memory_type="preference"
)

memories = integration.recall(
    query="efficient workflows",
    limit=5
)

context = integration.get_context()

# ─── Vision Analysis ─────────────────────────
screen_info = integration.analyze_screen()
text = integration.read_screen()
elements = integration.detect_ui_elements()
error = integration.detect_errors()

# ─── Comprehensive Context ───────────────────
full_context = integration.get_agent_context()
# Returns: recent_memories, screen_analysis, available_tools, etc.
```

---

## 5. Integration with Main Agent

### In your `agent.py` or `main.py`:

```python
from core.advanced_integration import get_integration

# Initialize integration when agent starts
integration = get_integration()

# Before processing user command:
context = integration.get_agent_context()

# When agent needs to recall something:
memories = integration.recall(
    query="related to user request",
    limit=3
)

# When agent needs to understand screen:
screen = integration.analyze_screen()

# When agent executes a tool:
result = integration.execute_tool(
    tool_name="browser_search",
    query=user_query
)

# When agent learns something:
integration.remember(
    content=f"User asked about: {topic}",
    memory_type="conversation"
)
```

---

## 6. Configuration Files

### `~/.jarvis/plugins/` Directory Structure

```
~/.jarvis/
├── plugins/
│   ├── web_browser.json          # Plugin configs
│   ├── system_control.json
│   └── memory_tools.json
└── memory/
    ├── advanced_memory.db
    ├── jarvis_memory.sqlite
    └── chroma_db/
```

### Plugin Configuration Format

```json
{
  "timeout": 30,
  "enabled": true,
  "api_key": "sk-...",
  "custom_settings": {
    "option1": "value1"
  }
}
```

---

## 7. Performance Considerations

### Plugin System
- Lazy loading of plugins (only when needed)
- Dependency resolution prevents circular dependencies
- Tool caching for O(1) lookup

### Memory System
- SQLite with indexes for fast search
- Relevance scoring prioritizes important memories
- Periodic consolidation reduces database size
- Access-based decay naturally prunes old memories

### Vision System
- Screenshot compression (JPEG, quality 85)
- Resolution limiting (max 1280px width)
- Model inference runs on local Ollama (GPU-accelerated if available)
- Analysis caching and history tracking

---

## 8. Troubleshooting

### Plugin Not Loading
```python
registry = get_plugin_registry()
status = registry.get_plugin_status("my_plugin")
print(f"Status: {status}")

# Check logs
import logging
logging.getLogger("jarvis").setLevel(logging.DEBUG)
```

### Memory Search Not Finding Results
- Ensure memories are being stored with correct types/tags
- Check relevance scores (default min is 0.3)
- Review memory consolidation log

### Vision Analysis Failing
- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- Check model is installed: `ollama list`
- Verify OLLAMA_URL environment variable if using custom server

---

## 9. Future Enhancements

- [ ] Plugin marketplace and auto-installation
- [ ] Advanced NLP for memory search (sentence transformers)
- [ ] Vision model fine-tuning on app-specific tasks
- [ ] Cross-memory relationship inference
- [ ] Plugin update checking and auto-updates
- [ ] Memory backup and versioning
- [ ] Vision model caching for repeated screens

---

## Summary

These three systems work together to create a powerful, extensible AI assistant:

1. **Plugins** provide modular functionality
2. **Memory** provides contextual understanding and learning
3. **Vision** provides screen awareness
4. **Integration** ties everything together seamlessly

The architecture is designed to be:
- **Extensible**: Add new plugins and capabilities easily
- **Performant**: Caching and indexing for fast operations
- **Reliable**: Error handling and logging throughout
- **User-friendly**: Configured via JSON, no code changes needed
