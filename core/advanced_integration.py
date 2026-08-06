"""
J.A.R.V.I.S. Advanced Features Integration
Bridges the plugin system, advanced memory, and vision system with the main agent.
"""

import os
import logging
from typing import Dict, List, Any, Optional, Callable
from functools import wraps

from core.plugin_loader import get_plugin_registry, PluginRegistry
from core.advanced_memory import get_memory_manager, EnhancedMemoryManager, MemoryType
from core.advanced_vision import get_vision_system, AdvancedVisionSystem

logger = logging.getLogger(__name__)


class AdvancedFeaturesIntegration:
    """
    Central integration point for all advanced features.
    Provides unified interface for agent to use plugins, memory, and vision.
    """
    
    def __init__(self):
        self.plugin_registry: PluginRegistry = get_plugin_registry()
        self.memory_manager: EnhancedMemoryManager = get_memory_manager()
        self.vision_system: AdvancedVisionSystem = get_vision_system()
        
        self._tool_cache: Dict[str, Callable] = {}
        self._initialize()
    
    def _initialize(self):
        """Initialize all systems and load enabled plugins."""
        logger.info("Initializing advanced features integration...")
        
        # Load default enabled plugins
        for plugin_info in self.plugin_registry.list_plugins():
            if plugin_info["metadata"]["enabled"]:
                plugin_name = plugin_info["name"]
                config = self._load_plugin_config(plugin_name)
                self.plugin_registry.load_plugin(plugin_name, config)
        
        # Cache all available tools
        self._refresh_tool_cache()
        logger.info("✓ Advanced features initialized")
    
    def _load_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """Load configuration for a plugin."""
        config_file = os.path.join(
            os.path.expanduser("~"),
            ".jarvis",
            "plugins",
            f"{plugin_name}.json"
        )
        
        if os.path.exists(config_file):
            try:
                import json
                with open(config_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load config for '{plugin_name}': {e}")
        
        return {}
    
    def _refresh_tool_cache(self):
        """Update the tool cache with all available tools from plugins."""
        self._tool_cache.clear()
        
        all_tools = self.plugin_registry.get_all_tools()
        for plugin_name, tools in all_tools.items():
            for tool in tools:
                tool_name = getattr(tool, "_tool_name", tool.__name__)
                self._tool_cache[tool_name] = tool
        
        logger.info(f"Tool cache refreshed: {len(self._tool_cache)} tools available")
    
    # ─── Plugin Management ──────────────────────────────────
    
    def get_available_tools(self) -> Dict[str, Callable]:
        """Get all available tools from loaded plugins."""
        return self._tool_cache.copy()
    
    def get_tool(self, tool_name: str) -> Optional[Callable]:
        """Get a specific tool by name."""
        return self._tool_cache.get(tool_name)
    
    def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """
        Execute a plugin tool with given arguments.
        
        Args:
            tool_name: Name of the tool to execute
            **kwargs: Arguments for the tool
            
        Returns:
            Tool execution result
        """
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        try:
            result = tool(**kwargs)
            
            # Log tool execution to memory
            self.memory_manager.store_memory(
                content=f"Executed tool: {tool_name} with args: {kwargs}",
                memory_type=MemoryType.WORKFLOW,
                tags=["tool_execution", tool_name],
                metadata={"result": str(result)[:200]}
            )
            
            return result
        except Exception as e:
            logger.error(f"Tool execution failed for '{tool_name}': {e}")
            raise
    
    def load_plugin(self, plugin_name: str, config: Dict[str, Any] = None) -> bool:
        """Load a plugin dynamically."""
        success = self.plugin_registry.load_plugin(plugin_name, config)
        if success:
            self._refresh_tool_cache()
        return success
    
    def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin."""
        success = self.plugin_registry.unload_plugin(plugin_name)
        if success:
            self._refresh_tool_cache()
        return success
    
    def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a plugin."""
        success = self.plugin_registry.reload_plugin(plugin_name)
        if success:
            self._refresh_tool_cache()
        return success
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all plugins with their status."""
        return self.plugin_registry.list_plugins()
    
    # ─── Memory Management ──────────────────────────────────
    
    def remember(
        self,
        content: str,
        memory_type: str = "context",
        tags: List[str] = None,
        metadata: Dict[str, Any] = None,
    ) -> str:
        """
        Store something in memory.
        
        Args:
            content: What to remember
            memory_type: Type of memory (conversation, preference, skill, error, workflow, etc.)
            tags: Tags for categorization
            metadata: Additional metadata
            
        Returns:
            Memory ID
        """
        try:
            mtype = MemoryType(memory_type)
        except ValueError:
            mtype = MemoryType.CONTEXT
        
        memory = self.memory_manager.store_memory(
            content=content,
            memory_type=mtype,
            tags=tags or [],
            metadata=metadata or {}
        )
        
        return memory.id
    
    def recall(
        self,
        query: str,
        memory_type: str = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search and recall memories.
        
        Args:
            query: Search query
            memory_type: Filter by memory type
            limit: Maximum results
            
        Returns:
            List of matching memories
        """
        mtype = None
        if memory_type:
            try:
                mtype = MemoryType(memory_type)
            except ValueError:
                pass
        
        memories = self.memory_manager.search_memories(
            query=query,
            memory_type=mtype,
            limit=limit
        )
        
        return [m.to_dict() for m in memories]
    
    def get_context(self, num_recent: int = 3) -> List[Dict[str, Any]]:
        """Get recent context memories."""
        memories = self.memory_manager.get_context_memories(num_recent)
        return [m.to_dict() for m in memories]
    
    def link_memories(self, from_id: str, to_id: str, relationship: str):
        """Create a relationship between two memories."""
        self.memory_manager.link_memories(from_id, to_id, relationship)
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get statistics about the memory system."""
        return self.memory_manager.get_memory_stats()
    
    # ─── Vision System ──────────────────────────────────────
    
    def analyze_screen(self) -> Dict[str, Any]:
        """
        Analyze the current screen with full detail.
        
        Returns:
            Comprehensive screen analysis
        """
        analysis = self.vision_system.analyze_screen_comprehensive()
        
        # Store in memory
        self.memory_manager.store_memory(
            content=f"Screen analysis: {analysis.description}",
            memory_type=MemoryType.CONTEXT,
            tags=["screen_analysis"],
            metadata={
                "error_detected": analysis.error_detected,
                "num_ui_elements": len(analysis.ui_elements)
            }
        )
        
        return {
            "raw_text": analysis.raw_text,
            "description": analysis.description,
            "ui_elements": [e.to_dict() for e in analysis.ui_elements],
            "error_detected": analysis.error_detected,
            "error_message": analysis.error_message,
            "suggestions": analysis.suggestions,
        }
    
    def read_screen(self) -> str:
        """Get readable text from current screen."""
        analysis = self.vision_system.analyze_screen_comprehensive()
        return analysis.raw_text
    
    def detect_ui_elements(self) -> List[Dict[str, Any]]:
        """Detect all UI elements on current screen."""
        analysis = self.vision_system.analyze_screen_comprehensive()
        return [e.to_dict() for e in analysis.ui_elements]
    
    def detect_errors(self) -> Optional[str]:
        """Detect if there are errors on screen."""
        analysis = self.vision_system.analyze_screen_comprehensive()
        if analysis.error_detected:
            return analysis.error_message
        return None
    
    def get_screen_layout(self) -> str:
        """Get description of current screen layout."""
        analysis = self.vision_system.analyze_screen_comprehensive()
        return analysis.description
    
    # ─── Unified Context ────────────────────────────────────
    
    def get_agent_context(self) -> Dict[str, Any]:
        """
        Get complete context for agent decision making.
        Combines recent memories, screen analysis, and available tools.
        """
        return {
            "recent_memories": self.get_context(num_recent=3),
            "screen_analysis": self.analyze_screen(),
            "available_tools": list(self._tool_cache.keys()),
            "loaded_plugins": [p["name"] for p in self.list_plugins()],
            "memory_stats": self.get_memory_stats(),
        }


# Global integration instance
_integration = None


def get_integration() -> AdvancedFeaturesIntegration:
    """Get or create global integration instance."""
    global _integration
    if _integration is None:
        _integration = AdvancedFeaturesIntegration()
    return _integration


# ─── Decorator for automatic tool registration ──────────────────────

def jarvis_tool(
    name: str = None,
    description: str = "",
    tags: List[str] = None,
):
    """
    Decorator to register a function as a Jarvis tool.
    
    Example:
        @jarvis_tool(name="my_tool", description="Does something useful")
        def my_function(arg1: str, arg2: int = 5) -> str:
            return f"Result: {arg1} {arg2}"
    """
    def decorator(func: Callable) -> Callable:
        func._is_jarvis_tool = True
        func._tool_name = name or func.__name__
        func._tool_description = description
        func._tool_tags = tags or []
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        # Preserve tool metadata on wrapper
        for attr in ["_is_jarvis_tool", "_tool_name", "_tool_description", "_tool_tags"]:
            setattr(wrapper, attr, getattr(func, attr))
        
        return wrapper
    
    return decorator
