"""
Universal Executor for Jarvis
Converts natural language commands to executable actions.
Supports "order anything and it performs" paradigm with safety checks.
"""

import os
import logging
import json
import subprocess
from typing import List, Dict, Any, Optional, Callable, Tuple
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """Types of commands the executor can handle."""
    SYSTEM = "system"           # OS commands
    APPLICATION = "application" # App launch/control
    FILE = "file"               # File operations
    WEB = "web"                 # Web browsing/search
    MEDIA = "media"             # Audio/video playback
    PRODUCTIVITY = "productivity"  # Email, calendar, etc.
    DEVELOPMENT = "development"  # Git, build, deploy
    INFORMATION = "information" # Query info
    WORKFLOW = "workflow"       # Multi-step workflows


class ExecutionRisk(Enum):
    """Risk levels for command execution."""
    SAFE = "safe"               # No risk
    LOW = "low"                 # Minor impact
    MEDIUM = "medium"           # Moderate impact
    HIGH = "high"               # Significant impact
    CRITICAL = "critical"       # Could cause damage


class CommandExecutor:
    """
    Converts natural language to executable actions.
    Features:
    - Semantic understanding of commands
    - Risk assessment and confirmation
    - Safe execution with rollback
    - Fallback chains and retry
    """
    
    def __init__(self):
        self.command_registry: Dict[str, Dict[str, Any]] = {}
        self.execution_history: List[Dict[str, Any]] = []
        self.require_confirmation = True
        self.max_retries = 3
        
        # Safety
        self.blacklist = self._init_blacklist()
        self.whitelist = self._init_whitelist()
        
        # Callbacks
        self.on_confirmation_needed = None
        self.on_execution_start = None
        self.on_execution_complete = None
        self.on_error = None
    
    def _init_blacklist(self) -> set:
        """Initialize blacklisted commands."""
        return {
            "rm -rf /",
            "format c:",
            "del /s /q",
            "mkfs",
            "dd if=/dev/zero",
            "destroy",
            "wipe",
            "erase",
            "uninstall os",
        }
    
    def _init_whitelist(self) -> set:
        """Initialize whitelisted safe commands."""
        return {
            "ls", "dir", "cat", "type", "echo", "pwd",
            "mkdir", "cd", "find", "grep", "select-string",
            "get-childitem", "test-path",
        }
    
    def register_command(
        self,
        command_id: str,
        description: str,
        handler: Callable,
        risk_level: ExecutionRisk = ExecutionRisk.SAFE,
        requires_confirmation: bool = False,
        parameters: List[Dict] = None,
    ):
        """
        Register a command that the executor can handle.
        
        Args:
            command_id: Unique command identifier
            description: Human-readable description
            handler: Callable that executes the command
            risk_level: Risk level of this command
            requires_confirmation: Whether to ask user before executing
            parameters: List of expected parameters
        """
        self.command_registry[command_id] = {
            "description": description,
            "handler": handler,
            "risk_level": risk_level,
            "requires_confirmation": requires_confirmation,
            "parameters": parameters or [],
        }
        logger.info(f"Registered command: {command_id}")
    
    def execute(
        self,
        natural_language_command: str,
        context: Dict[str, Any] = None,
        user_confirmed: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a natural language command.
        
        Args:
            natural_language_command: User's natural language command
            context: Execution context
            user_confirmed: Whether user already confirmed execution
            
        Returns:
            Execution result with status and output
        """
        # Parse command
        parsed = self._parse_command(natural_language_command, context or {})
        
        if not parsed["success"]:
            return {
                "success": False,
                "error": parsed["error"],
                "timestamp": datetime.now().isoformat(),
            }
        
        command_info = parsed["command_info"]
        command_id = parsed["command_id"]
        parameters = parsed["parameters"]
        risk_level = command_info.get("risk_level", ExecutionRisk.SAFE)
        
        # Risk assessment
        if not self._assess_safety(parsed["command_text"], risk_level):
            return {
                "success": False,
                "error": "Command blocked by safety policy",
                "risk_level": risk_level.value,
                "timestamp": datetime.now().isoformat(),
            }
        
        # Request confirmation for risky commands
        if not user_confirmed and (
            risk_level in [ExecutionRisk.MEDIUM, ExecutionRisk.HIGH, ExecutionRisk.CRITICAL]
            or command_info.get("requires_confirmation")
        ):
            return {
                "success": False,
                "requires_confirmation": True,
                "command_id": command_id,
                "parameters": parameters,
                "risk_level": risk_level.value,
                "description": command_info.get("description"),
                "timestamp": datetime.now().isoformat(),
            }
        
        # Execute
        return self._execute_command(command_id, parameters, context or {})
    
    def _parse_command(
        self,
        command_text: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Parse natural language command.
        
        Returns:
            Parsed command info or error
        """
        command_text = command_text.strip().lower()
        
        # Try exact match
        for cmd_id, cmd_info in self.command_registry.items():
            description = cmd_info.get("description", "").lower()
            if command_text in description or description in command_text:
                return {
                    "success": True,
                    "command_id": cmd_id,
                    "command_info": cmd_info,
                    "command_text": command_text,
                    "parameters": self._extract_parameters(command_text, cmd_info),
                }
        
        # Try semantic matching
        matches = self._semantic_match(command_text)
        if matches:
            best_match = matches[0]
            return {
                "success": True,
                "command_id": best_match["command_id"],
                "command_info": best_match["command_info"],
                "command_text": command_text,
                "parameters": self._extract_parameters(command_text, best_match["command_info"]),
            }
        
        return {
            "success": False,
            "error": f"Unknown command: {command_text}",
        }
    
    def _semantic_match(self, command_text: str) -> List[Dict[str, Any]]:
        """
        Semantically match command to registered commands.
        Returns sorted by similarity score.
        """
        matches = []
        
        # Simple keyword matching
        keywords = set(command_text.split())
        
        for cmd_id, cmd_info in self.command_registry.items():
            description = cmd_info.get("description", "").lower()
            desc_keywords = set(description.split())
            
            # Calculate overlap
            overlap = len(keywords & desc_keywords)
            if overlap > 0:
                matches.append({
                    "command_id": cmd_id,
                    "command_info": cmd_info,
                    "score": overlap / max(len(keywords), len(desc_keywords)),
                })
        
        # Sort by score
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches
    
    def _extract_parameters(
        self,
        command_text: str,
        command_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Extract parameters from command text."""
        parameters = {}
        
        # Extract known parameter patterns
        for param in command_info.get("parameters", []):
            param_name = param.get("name")
            param_pattern = param.get("pattern")
            
            if param_pattern:
                import re
                match = re.search(param_pattern, command_text)
                if match:
                    parameters[param_name] = match.group(1)
        
        return parameters
    
    def _assess_safety(self, command_text: str, risk_level: ExecutionRisk) -> bool:
        """
        Assess if command is safe to execute.
        
        Returns:
            True if safe, False if blocked
        """
        # Check blacklist
        for blacklisted in self.blacklist:
            if blacklisted in command_text:
                logger.warning(f"Blocked blacklisted command: {command_text}")
                return False
        
        # Check risk level
        if risk_level == ExecutionRisk.CRITICAL:
            logger.warning(f"Blocked critical risk command: {command_text}")
            return False
        
        return True
    
    def _execute_command(
        self,
        command_id: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute registered command.
        Implements retry and error handling.
        """
        command_info = self.command_registry[command_id]
        handler = command_info["handler"]
        
        if self.on_execution_start:
            self.on_execution_start(command_id, parameters)
        
        result = {
            "command_id": command_id,
            "parameters": parameters,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Execute with retry
        last_error = None
        for attempt in range(self.max_retries):
            try:
                output = handler(parameters, context)
                
                result["success"] = True
                result["output"] = output
                result["attempts"] = attempt + 1
                
                if self.on_execution_complete:
                    self.on_execution_complete(command_id, result)
                
                self.execution_history.append(result)
                return result
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Execution attempt {attempt + 1} failed: {e}")
                
                if attempt < self.max_retries - 1:
                    continue  # Retry
                else:
                    break  # Give up
        
        # All retries failed
        result["success"] = False
        result["error"] = last_error
        result["attempts"] = self.max_retries
        
        if self.on_error:
            self.on_error(command_id, result)
        
        self.execution_history.append(result)
        return result
    
    def confirm_and_execute(
        self,
        command_id: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Confirm execution and execute command.
        Used after user confirmation.
        """
        return self._execute_command(command_id, parameters, context or {})
    
    def get_execution_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get execution history."""
        return self.execution_history[-limit:]
    
    def get_available_commands(self) -> List[Dict[str, str]]:
        """Get list of available commands."""
        return [
            {
                "id": cmd_id,
                "description": info.get("description"),
                "risk_level": info.get("risk_level", ExecutionRisk.SAFE).value,
            }
            for cmd_id, info in self.command_registry.items()
        ]
    
    def export_history(self) -> Dict[str, Any]:
        """Export execution history."""
        return {
            "timestamp": datetime.now().isoformat(),
            "total_executions": len(self.execution_history),
            "successful": sum(1 for e in self.execution_history if e.get("success")),
            "failed": sum(1 for e in self.execution_history if not e.get("success")),
            "history": self.get_execution_history(),
        }


class WorkflowBuilder:
    """
    Build multi-step workflows from natural language.
    Combines multiple commands into coherent workflows.
    """
    
    def __init__(self, executor: CommandExecutor):
        self.executor = executor
        self.workflows: Dict[str, Dict[str, Any]] = {}
    
    def build_workflow(
        self,
        description: str,
        steps: List[str],
    ) -> Dict[str, Any]:
        """
        Build a workflow from description and steps.
        
        Args:
            description: Workflow description
            steps: List of command steps
            
        Returns:
            Workflow definition
        """
        workflow = {
            "description": description,
            "steps": steps,
            "created_at": datetime.now().isoformat(),
            "status": "created",
        }
        
        return workflow
    
    def execute_workflow(
        self,
        workflow: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute a workflow step by step.
        
        Returns:
            Workflow execution result
        """
        result = {
            "workflow": workflow,
            "start_time": datetime.now().isoformat(),
            "steps_completed": 0,
            "steps_results": [],
        }
        
        for step_idx, step_command in enumerate(workflow.get("steps", [])):
            # Execute step
            step_result = self.executor.execute(step_command, context or {})
            result["steps_results"].append(step_result)
            
            if not step_result.get("success"):
                result["status"] = "failed"
                result["failed_step"] = step_idx
                break
            
            result["steps_completed"] = step_idx + 1
        
        if result.get("failed_step") is None:
            result["status"] = "completed"
        
        result["end_time"] = datetime.now().isoformat()
        return result


# Global instance
_executor = None


def get_command_executor() -> CommandExecutor:
    """Get or create global executor instance."""
    global _executor
    if _executor is None:
        _executor = CommandExecutor()
    return _executor
