"""
J.A.R.V.I.S. Plugin Loader & Management System
Enables dynamic plugin loading, versioning, and dependency resolution.
"""

import os
import json
import importlib.util
import logging
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PluginStatus(Enum):
    """Plugin lifecycle status."""
    DISABLED = "disabled"
    LOADING = "loading"
    ACTIVE = "active"
    ERROR = "error"
    OUTDATED = "outdated"


@dataclass
class PluginMetadata:
    """Plugin configuration and metadata."""
    name: str
    version: str
    description: str
    author: str
    entry_point: str  # e.g., "plugins.web_browser:WebBrowserPlugin"
    dependencies: List[str]  # Other plugins this depends on
    min_python_version: str = "3.9"
    max_python_version: Optional[str] = None
    enabled: bool = True
    config_schema: Dict[str, Any] = None
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "PluginMetadata":
        """Load plugin metadata from JSON."""
        return cls(**data)
    
    def to_json(self) -> Dict[str, Any]:
        """Serialize plugin metadata to JSON."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "entry_point": self.entry_point,
            "dependencies": self.dependencies,
            "min_python_version": self.min_python_version,
            "max_python_version": self.max_python_version,
            "enabled": self.enabled,
            "config_schema": self.config_schema,
        }


class PluginRegistry:
    """Central registry for all plugins with lifecycle management."""
    
    def __init__(self, plugins_dir: str = None):
        self.plugins_dir = plugins_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "plugins"
        )
        self.config_dir = os.path.join(os.path.expanduser("~"), ".jarvis", "plugins")
        os.makedirs(self.config_dir, exist_ok=True)
        
        self.registry: Dict[str, Dict[str, Any]] = {}
        self.loaded_plugins: Dict[str, Any] = {}
        self.plugin_tools: Dict[str, List[Callable]] = {}
        self._load_plugin_registry()
    
    def _load_plugin_registry(self):
        """Scan and load plugin metadata from plugin.json files."""
        for plugin_path in Path(self.plugins_dir).glob("plugin.json"):
            try:
                with open(plugin_path, "r") as f:
                    config = json.load(f)
                    metadata = PluginMetadata.from_json(config)
                    self.registry[metadata.name] = {
                        "metadata": metadata,
                        "path": str(plugin_path.parent),
                        "status": PluginStatus.DISABLED,
                    }
                    logger.info(f"Registered plugin: {metadata.name} v{metadata.version}")
            except Exception as e:
                logger.error(f"Failed to load plugin metadata from {plugin_path}: {e}")
    
    def load_plugin(self, plugin_name: str, config: Dict[str, Any] = None) -> bool:
        """
        Dynamically load a plugin and its tools.
        
        Args:
            plugin_name: Name of the plugin to load
            config: Plugin configuration overrides
            
        Returns:
            True if successfully loaded, False otherwise
        """
        if plugin_name not in self.registry:
            logger.error(f"Plugin '{plugin_name}' not found in registry")
            return False
        
        if plugin_name in self.loaded_plugins:
            logger.warning(f"Plugin '{plugin_name}' is already loaded")
            return True
        
        plugin_info = self.registry[plugin_name]
        metadata = plugin_info["metadata"]
        
        # Check dependencies
        if not self._resolve_dependencies(plugin_name):
            plugin_info["status"] = PluginStatus.ERROR
            logger.error(f"Failed to resolve dependencies for '{plugin_name}'")
            return False
        
        try:
            plugin_info["status"] = PluginStatus.LOADING
            
            # Load the plugin module
            module = self._load_plugin_module(metadata.entry_point, plugin_info["path"])
            if not module:
                raise ImportError(f"Failed to import plugin module: {metadata.entry_point}")
            
            # Initialize plugin instance if it has a constructor
            plugin_class = getattr(module, self._get_class_name(metadata.entry_point), None)
            if plugin_class:
                # Merge user config with defaults
                final_config = config or {}
                plugin_instance = plugin_class(config=final_config)
            else:
                plugin_instance = module
            
            self.loaded_plugins[plugin_name] = plugin_instance
            plugin_info["status"] = PluginStatus.ACTIVE
            
            # Extract and register tools from the plugin
            self._extract_plugin_tools(plugin_name, module)
            
            logger.info(f"✓ Plugin '{plugin_name}' loaded successfully")
            return True
            
        except Exception as e:
            plugin_info["status"] = PluginStatus.ERROR
            logger.error(f"Failed to load plugin '{plugin_name}': {e}", exc_info=True)
            return False
    
    def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin and clean up resources."""
        if plugin_name not in self.loaded_plugins:
            logger.warning(f"Plugin '{plugin_name}' is not loaded")
            return False
        
        try:
            plugin = self.loaded_plugins[plugin_name]
            
            # Call cleanup if available
            if hasattr(plugin, "cleanup"):
                plugin.cleanup()
            
            del self.loaded_plugins[plugin_name]
            if plugin_name in self.plugin_tools:
                del self.plugin_tools[plugin_name]
            
            if plugin_name in self.registry:
                self.registry[plugin_name]["status"] = PluginStatus.DISABLED
            
            logger.info(f"✓ Plugin '{plugin_name}' unloaded")
            return True
        except Exception as e:
            logger.error(f"Error unloading plugin '{plugin_name}': {e}")
            return False
    
    def _resolve_dependencies(self, plugin_name: str, visited: set = None) -> bool:
        """Recursively resolve and load plugin dependencies."""
        if visited is None:
            visited = set()
        
        if plugin_name in visited:
            return True  # Circular dependency or already processed
        
        visited.add(plugin_name)
        
        metadata = self.registry[plugin_name]["metadata"]
        for dep in metadata.dependencies:
            if dep not in self.loaded_plugins:
                if not self.load_plugin(dep):
                    return False
        
        return True
    
    def _load_plugin_module(self, entry_point: str, plugin_path: str):
        """Load a plugin module from entry point string."""
        try:
            module_name, class_name = entry_point.split(":")
            module_file = os.path.join(plugin_path, module_name.replace(".", os.sep) + ".py")
            
            spec = importlib.util.spec_from_file_location(module_name, module_file)
            if not spec or not spec.loader:
                return None
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            logger.error(f"Failed to load module '{entry_point}': {e}")
            return None
    
    def _get_class_name(self, entry_point: str) -> str:
        """Extract class name from entry point."""
        return entry_point.split(":")[-1]
    
    def _extract_plugin_tools(self, plugin_name: str, module):
        """Extract tool functions from a plugin module."""
        tools = []
        for name in dir(module):
            obj = getattr(module, name)
            if callable(obj) and hasattr(obj, "_is_jarvis_tool"):
                tools.append(obj)
        
        if tools:
            self.plugin_tools[plugin_name] = tools
            logger.info(f"  Extracted {len(tools)} tools from '{plugin_name}'")
    
    def get_all_tools(self) -> Dict[str, List[Callable]]:
        """Get all available tools from loaded plugins."""
        return self.plugin_tools.copy()
    
    def get_plugin_status(self, plugin_name: str) -> Optional[PluginStatus]:
        """Get the current status of a plugin."""
        if plugin_name in self.registry:
            return self.registry[plugin_name]["status"]
        return None
    
    def list_plugins(self, status_filter: PluginStatus = None) -> List[Dict[str, Any]]:
        """List all registered plugins with optional status filter."""
        plugins = []
        for name, info in self.registry.items():
            if status_filter is None or info["status"] == status_filter:
                plugins.append({
                    "name": name,
                    "status": info["status"].value,
                    "metadata": info["metadata"].to_json(),
                })
        return plugins
    
    def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a plugin (unload and reload)."""
        config = self._get_plugin_config(plugin_name)
        self.unload_plugin(plugin_name)
        return self.load_plugin(plugin_name, config)
    
    def _get_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """Load plugin configuration from disk."""
        config_file = os.path.join(self.config_dir, f"{plugin_name}.json")
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load config for '{plugin_name}': {e}")
        return {}
    
    def save_plugin_config(self, plugin_name: str, config: Dict[str, Any]):
        """Save plugin configuration to disk."""
        config_file = os.path.join(self.config_dir, f"{plugin_name}.json")
        try:
            with open(config_file, "w") as f:
                json.dump(config, f, indent=2)
            logger.info(f"Saved config for plugin '{plugin_name}'")
        except Exception as e:
            logger.error(f"Failed to save config for '{plugin_name}': {e}")


# Global plugin registry
_plugin_registry = None


def get_plugin_registry() -> PluginRegistry:
    """Get the global plugin registry instance."""
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry()
    return _plugin_registry
