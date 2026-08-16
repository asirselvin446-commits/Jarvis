"""
J.A.R.V.I.S. Tool Manager
═════════════════════════
Discovers, registers, and executes plugins dynamically.
Formats tools into OpenAI JSON schema for LLMs (Claude, Gemini, Qwen).
Supports hot-loading, hot-unloading, and lifecycle hooks (PreToolUse, PostToolUse, OnToolError).
"""

import os
import sys
import importlib
import importlib.util
import inspect
from typing import Callable, Dict, Any, List, Optional

# Global registry of tools
_TOOL_REGISTRY: Dict[str, dict] = {}


def tool(name: str, description: str, parameters: dict, requires_confirmation: bool = False, is_dangerous: bool = False):
    """
    Decorator to register a function as a tool.
    :param name: Name of the tool.
    :param description: Description of what the tool does.
    :param parameters: Dict describing the arguments (OpenAI function calling format).
    :param requires_confirmation: If True, the agent must ask the user before executing.
    :param is_dangerous: If True, denotes a system-modifying tool that requires extra scrutiny.
    """
    def decorator(func: Callable):
        module = inspect.getmodule(func)
        module_name = module.__name__ if module else "unknown"
        _TOOL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "requires_confirmation": requires_confirmation,
            "is_dangerous": is_dangerous,
            "func": func,
            "module_name": module_name
        }
        return func
    return decorator


class ToolManager:
    def __init__(self, plugins_dir: str = "plugins", workspace: str = "default"):
        # Resolve path for PyInstaller
        if getattr(sys, 'frozen', False):
            self.plugins_dir = os.path.join(sys._MEIPASS, plugins_dir)
        else:
            self.plugins_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), plugins_dir)
            
        self.workspace = workspace
        self.tools = _TOOL_REGISTRY
        self._hooks: Dict[str, List[Callable]] = {
            "PreToolUse": [],
            "PostToolUse": [],
            "OnToolError": []
        }
        self._discover_plugins()

    def register_hook(self, stage: str, callback: Callable):
        """
        Register a lifecycle hook inspired by Claude Code plugins.
        Stages: 'PreToolUse', 'PostToolUse', 'OnToolError'
        """
        if stage in self._hooks:
            self._hooks[stage].append(callback)

    def _run_hooks(self, stage: str, **kwargs):
        """Run all registered hooks for a given lifecycle stage."""
        for hook in self._hooks.get(stage, []):
            try:
                hook(**kwargs)
            except Exception as e:
                print(f"[ToolManager] Hook error in {stage}: {e}")

    def get_workspace_dir(self) -> str:
        ws_dir = os.path.join(os.path.expanduser("~"), ".jarvis", "workspaces", self.workspace, "skills")
        os.makedirs(ws_dir, exist_ok=True)
        return ws_dir

    def set_workspace(self, workspace_name: str):
        print(f"[ToolManager] Switching workspace to: {workspace_name}")
        self.workspace = workspace_name
        self.reload_plugins()

    def _load_from_path(self, module_name: str, file_path: str):
        """Helper to load a python file dynamically from an absolute path."""
        try:
            already_loaded = module_name in sys.modules
            if already_loaded:
                importlib.reload(sys.modules[module_name])
                print(f"[ToolManager] Hot-reloaded: {module_name}")
            else:
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    print(f"[ToolManager] Loaded: {module_name}")
        except Exception as e:
            print(f"[ToolManager] Failed to load {module_name}: {e}")

    def _discover_plugins(self):
        """Dynamically load all python files in the plugins directory and subdirectories."""
        if not os.path.exists(self.plugins_dir):
            print(f"[ToolManager] Warning: Plugins directory not found at {self.plugins_dir}")
            return

        base = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if base not in sys.path:
            sys.path.insert(0, base)

        # 1. Load core global plugins
        for root, _, files in os.walk(self.plugins_dir):
            for filename in files:
                if filename.endswith(".py") and not filename.startswith("__"):
                    rel_path = os.path.relpath(os.path.join(root, filename), self.plugins_dir)
                    module_parts = ["plugins"] + rel_path[:-3].replace("\\", "/").split("/")
                    module_name = ".".join(module_parts)
                    try:
                        if module_name in sys.modules:
                            importlib.reload(sys.modules[module_name])
                        else:
                            importlib.import_module(module_name)
                            print(f"[ToolManager] Loaded core plugin: {module_name}")
                    except Exception as e:
                        print(f"[ToolManager] Failed to load core plugin {module_name}: {e}")

        # 2. Load active workspace skills
        ws_dir = self.get_workspace_dir()
        for root, _, files in os.walk(ws_dir):
            for filename in files:
                if filename.endswith(".py") and not filename.startswith("__"):
                    file_path = os.path.join(root, filename)
                    module_name = f"workspace_{self.workspace}.{filename[:-3]}"
                    self._load_from_path(module_name, file_path)

    def reload_plugins(self):
        """Hot-reload all plugins. Unloads missing ones, reloads existing, loads new."""
        print("[ToolManager] Hot-reloading plugins...")
        global _TOOL_REGISTRY
        _TOOL_REGISTRY.clear()
        self._discover_plugins()

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
        """Execute a tool by name with provided arguments and lifecycle hooks."""
        if name not in self.tools:
            return {"error": f"Tool '{name}' not found."}

        from core.control import get_control_plane
        control = get_control_plane()

        try:
            self._run_hooks("PreToolUse", tool_name=name, arguments=arguments)
            func = self.tools[name]["func"]
            result = func(**arguments)
            self._run_hooks("PostToolUse", tool_name=name, arguments=arguments, result=result)
            # Audit every executed tool (args redacted inside the control plane).
            control.audit(name, arguments, "ok")
            return result
        except Exception as e:
            self._run_hooks("OnToolError", tool_name=name, arguments=arguments, error=e)
            control.audit(name, arguments, f"error: {e}")
            return {"error": f"Execution failed for '{name}': {str(e)}"}
