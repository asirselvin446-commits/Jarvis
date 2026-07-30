"""
J.A.R.V.I.S. Base Agent
Abstract base class for all specialized agents in the multi-agent system.
Each agent has a name, capabilities, and access to shared tools and memory.
"""

import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from core.tool_manager import ToolManager
from core.memory import MemoryManager
from core.verification_agent import VerificationAgent
from core.llm_provider import llm_chat


class AgentResult:
    """Standardized result from any agent execution."""

    def __init__(self, success: bool, response: str, agent_name: str,
                 tool_results: Optional[List[dict]] = None, metadata: Optional[dict] = None,
                 response_stream: Optional[Any] = None):
        self.success = success
        self.response = response
        self.agent_name = agent_name
        self.tool_results = tool_results or []
        self.metadata = metadata or {}
        self.response_stream = response_stream

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "response": self.response,
            "agent_name": self.agent_name,
            "tool_results": self.tool_results,
            "metadata": self.metadata
        }


class BaseAgent(ABC):
    """
    Abstract base class for specialized agents.

    Subclasses must implement:
      - can_handle(task): Whether this agent can handle the task
      - execute(task, context): Perform the task and return AgentResult
    """

    def __init__(self, name: str, description: str, capabilities: List[str],
                 tool_manager: ToolManager, memory: MemoryManager):
        self.name = name
        self.description = description
        self.capabilities = capabilities
        self.tool_manager = tool_manager
        self.memory = memory
        self.verification = VerificationAgent()

    @abstractmethod
    def can_handle(self, task: str) -> float:
        """
        Return a confidence score (0.0 to 1.0) of how well this agent
        can handle the given task. 0 means cannot handle, 1 means perfect match.
        """
        pass

    @abstractmethod
    def execute(self, task: str, context: str = "") -> AgentResult:
        """Execute the task and return an AgentResult."""
        pass

    def _get_relevant_tools(self) -> List[dict]:
        """Get tool schemas relevant to this agent's capabilities."""
        all_schemas = self.tool_manager.get_tool_schemas()
        if not self.capabilities:
            return all_schemas

        relevant = []
        for schema in all_schemas:
            tool_name = schema["function"]["name"]
            if any(cap in tool_name for cap in self.capabilities):
                relevant.append(schema)
        return relevant if relevant else all_schemas

    def _call_llm(self, system_prompt: str, user_message: str,
                  tools: Optional[List[dict]] = None, temperature: float = 0.0) -> dict:
        """Call LLM with optional tool calling (auto-routes cloud/local)."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        return llm_chat(messages, tools=tools, temperature=temperature)

    def _execute_tool_calls(self, tool_calls: List[dict]) -> List[dict]:
        """Execute a list of tool calls and return results."""
        results = []
        for tc in tool_calls:
            try:
                tool_name = tc["function"]["name"]
                args = tc["function"]["arguments"]
                if isinstance(args, str):
                    args = json.loads(args)

                result = self.tool_manager.execute_tool(tool_name, args)
                success = self.verification.verify(tool_name, result)

                results.append({
                    "tool": tool_name,
                    "arguments": args,
                    "result": result,
                    "verified_success": success
                })
            except Exception as e:
                results.append({
                    "tool": tc.get("function", {}).get("name", "unknown"),
                    "result": f"Tool execution error: {str(e)}",
                    "verified_success": False
                })
        return results

    def __repr__(self):
        return f"<{self.__class__.__name__} name='{self.name}'>"
