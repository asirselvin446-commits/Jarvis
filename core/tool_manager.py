"""
J.A.R.V.I.S. Tool Manager
Discovers, registers, and executes plugins dynamically.
Formats tools into OpenAI JSON schema for Qwen 2.5 7B.
"""

import os
import sys
import importlib
import inspect
from typing import Callable, Dict, Any, List

# Global registry of tools
_TOOL_REGISTRY: Dict[str, dict] = {}


def tool(name: str, description: str, parameters: dict):
    """
    Decorator to register a function as a tool.
    :param name: Name of the tool.
    :param description: Description of what the tool does.
    :param parameters: Dict describing the arguments (OpenAI function calling format).
    """
    def decorator(func: Callable):
        _TOOL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "func": func
        }
        return func
    return decorator


class ToolManager:
    def __init__(self, plugins_dir: str = "plugins"):
        # Resolve path for PyInstaller
        if getattr(sys, 'frozen', False):
            self.plugins_dir = os.path.join(sys._MEIPASS, plugins_dir)
        else:
            self.plugins_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), plugins_dir)
            
        self.tools = _TOOL_REGISTRY
        self._discover_plugins()

    def _discover_plugins(self):
        """Dynamically load all python files in the plugins directory and subdirectories."""
        if not os.path.exists(self.plugins_dir):
            print(f"[ToolManager] Warning: Plugins directory not found at {self.plugins_dir}")
            return

        base = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if base not in sys.path:
            sys.path.insert(0, base)

        for root, _, files in os.walk(self.plugins_dir):
            for filename in files:
                if filename.endswith(".py") and not filename.startswith("__"):
                    rel_path = os.path.relpath(os.path.join(root, filename), self.plugins_dir)
                    module_parts = ["plugins"] + rel_path[:-3].replace("\\", "/").split("/")
                    module_name = ".".join(module_parts)
                    try:
                        importlib.import_module(module_name)
                        print(f"[ToolManager] Loaded plugin: {module_name}")
                    except Exception as e:
                        print(f"[ToolManager] Failed to load plugin {module_name}: {e}")

    def get_tool_schemas(self) -> List[dict]:
        """Return all registered tools formatted for LLM function calling."""
        schemas = []
        for name, data in self.tools.items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": data["name"],
                    "description": data["description"],
                    "parameters": data["parameters"]
                }
            })
        return schemas

    def execute_tool(self, name: str, arguments: dict) -> Any:
        """Execute a tool by name with provided arguments."""
        if name not in self.tools:
            return {"error": f"Tool '{name}' not found."}
            
        try:
            func = self.tools[name]["func"]
            result = func(**arguments)
            return result
        except Exception as e:
            return {"error": f"Execution failed for '{name}': {str(e)}"}
