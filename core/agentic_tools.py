"""
J.A.R.V.I.S. Agentic Tools Bridge
═══════════════════════════════════
Bridges the ToolManager plugin system into the ReAct agentic loop.
Instead of maintaining a separate tool registry, this module wraps
the ToolManager so the ReAct loop has access to ALL registered plugins.
"""

import logging
from typing import Dict, Any, List, Optional

from core.tool_manager import ToolManager

logger = logging.getLogger("jarvis.agentic_tools")


class AgenticToolRegistry:
    """
    Unified tool registry that delegates to the ToolManager.
    Provides the same interface the ReAct loop expects, but uses
    the single source of truth for all tools.
    """

    def __init__(self, tool_manager: Optional[ToolManager] = None):
        # Reuse an existing ToolManager (e.g. the Orchestrator's) when provided.
        # The tool registry is a module-level global, so constructing a new
        # ToolManager needlessly re-imports every plugin. Sharing avoids that.
        self._tool_manager = tool_manager or ToolManager()
        logger.info(
            "[AgenticTools] Bridged %d tools from ToolManager",
            len(self._tool_manager.tools),
        )

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Return tool schemas in the format expected by the ReAct loop prompt."""
        schemas = []
        for name, data in self._tool_manager.tools.items():
            schemas.append({
                "name": data["name"],
                "description": data["description"],
                "parameters": data["parameters"]
            })
        return schemas

    def get_tool_schemas_for_llm(self) -> List[Dict[str, Any]]:
        """Return tool schemas in OpenAI function-calling format for llm_chat()."""
        return self._tool_manager.get_tool_schemas()

    def execute(self, name: str, args: Dict[str, Any]) -> str:
        """Execute a tool by name with provided arguments."""
        if name not in self._tool_manager.tools:
            available = list(self._tool_manager.tools.keys())
            return f"Error: Tool '{name}' not found. Available tools: {available}"

        try:
            logger.info("[AgenticTool] Executing '%s' with args: %s", name, args)
            result = self._tool_manager.execute_tool(name, args)
            return str(result)
        except Exception as e:
            logger.error("[AgenticTool] Tool '%s' failed: %s", name, e)
            return f"Error executing tool '{name}': {e}"

    def list_tools(self) -> List[str]:
        """Return list of available tool names."""
        return list(self._tool_manager.tools.keys())

    def get_meta(self, name: str) -> Dict[str, Any]:
        """Return safety metadata for a tool (flags declared on the @tool decorator).

        Keys: ``is_dangerous``, ``requires_confirmation``. Unknown tools return
        an empty dict so callers can treat missing tools as non-dangerous.
        """
        data = self._tool_manager.tools.get(name)
        if not data:
            return {}
        return {
            "is_dangerous": bool(data.get("is_dangerous", False)),
            "requires_confirmation": bool(data.get("requires_confirmation", False)),
        }


# Global singleton instance
_registry_instance: Optional[AgenticToolRegistry] = None


def get_agentic_tools(tool_manager: Optional[ToolManager] = None) -> AgenticToolRegistry:
    """Return the shared agentic tool registry.

    Pass an existing ``ToolManager`` (such as the Orchestrator's) on first call
    so the ReAct loop and the Orchestrator share one plugin registry instead of
    each reloading every plugin.
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = AgenticToolRegistry(tool_manager=tool_manager)
    return _registry_instance
