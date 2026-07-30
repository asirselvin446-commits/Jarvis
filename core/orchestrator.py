"""
J.A.R.V.I.S. Orchestrator
Meta-agent that decomposes complex user requests into sub-tasks and
delegates them to the best-fit specialized agent. Supports parallel
execution via ThreadPoolExecutor.
"""

import json
import re
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

from core.base_agent import BaseAgent, AgentResult
from core.planner import Planner
from core.memory import MemoryManager
from core.tool_manager import ToolManager
from core.verification_agent import VerificationAgent
from core.message_bus import get_message_bus


class SystemAgent(BaseAgent):
    """
    The default catch-all agent. Handles any task by using the full
    planner + tool pipeline (the original OSKernel logic).
    """

    def __init__(self, tool_manager: ToolManager, memory: MemoryManager):
        super().__init__(
            name="system",
            description="General-purpose system agent that can execute any tool via the planner.",
            capabilities=[],  # Empty = all tools
            tool_manager=tool_manager,
            memory=memory
        )
        self.planner = Planner()

    def can_handle(self, task: str) -> float:
        """System agent is the fallback — can handle anything at low confidence."""
        return 0.3

    def execute(self, task: str, context: str = "") -> AgentResult:
        """Run the full planner pipeline."""
        tool_schemas = self.tool_manager.get_tool_schemas()
        plan_result = self.planner.plan_and_select_tools(task, context, tool_schemas)

        if plan_result["type"] == "tools":
            tool_results = self._execute_tool_calls(plan_result["tool_calls"])

            # Publish tool execution events to the bus
            bus = get_message_bus()
            for tr in tool_results:
                bus.publish("tool_executed", self.name, {
                    "tool": tr["tool"],
                    "success": tr["verified_success"]
                })

            try:
                response_stream = self.planner.evaluate_result_stream(task, tool_results)
                response = ""
            except Exception:
                response_stream = None
                response = ". ".join(str(tr.get("result", "Done")) for tr in tool_results)

            all_success = all(tr.get("verified_success", False) for tr in tool_results)
            return AgentResult(
                success=all_success,
                response=response,
                agent_name=self.name,
                tool_results=tool_results,
                response_stream=response_stream
            )

        elif plan_result["type"] == "response":
            return AgentResult(
                success=True,
                response=plan_result["content"],
                agent_name=self.name
            )
        else:
            return AgentResult(
                success=False,
                response=plan_result.get("content", "I couldn't process that."),
                agent_name=self.name
            )


class WebAgent(BaseAgent):
    """Specialized agent for web browsing, searching, and YouTube."""

    def __init__(self, tool_manager: ToolManager, memory: MemoryManager):
        super().__init__(
            name="web",
            description="Handles web searches, opening websites, YouTube playback.",
            capabilities=["search_google", "play_youtube", "search_youtube", "open_website"],
            tool_manager=tool_manager,
            memory=memory
        )
        self.planner = Planner()

    def can_handle(self, task: str) -> float:
        keywords = ["search", "google", "youtube", "website", "url", "browse",
                     "open youtube", "play on youtube", "web", "internet", "online"]
        task_lower = task.lower()
        matches = sum(1 for kw in keywords if kw in task_lower)
        return min(0.9, 0.1 + matches * 0.4)

    def execute(self, task: str, context: str = "") -> AgentResult:
        tool_schemas = self._get_relevant_tools()
        plan_result = self.planner.plan_and_select_tools(task, context, tool_schemas)

        if plan_result["type"] == "tools":
            tool_results = self._execute_tool_calls(plan_result["tool_calls"])
            bus = get_message_bus()
            bus.publish("web_action", self.name, {"task": task, "results": len(tool_results)})

            try:
                response_stream = self.planner.evaluate_result_stream(task, tool_results)
                response = ""
            except Exception:
                response_stream = None
                response = ". ".join(str(tr.get("result", "Done")) for tr in tool_results)

            return AgentResult(success=True, response=response,
                               agent_name=self.name, tool_results=tool_results,
                               response_stream=response_stream)

        return AgentResult(success=True, response=plan_result.get("content", "Done."),
                           agent_name=self.name)


class CodingAgent(BaseAgent):
    """Specialized agent for code operations, git, and VS Code."""

    def __init__(self, tool_manager: ToolManager, memory: MemoryManager):
        super().__init__(
            name="coding",
            description="Handles code reading, writing, searching, git operations, and code review.",
            capabilities=["read_code", "write_code", "search_code", "git_",
                           "execute_python", "list_directory", "open_in_vscode", "code_review"],
            tool_manager=tool_manager,
            memory=memory
        )
        self.planner = Planner()

    def can_handle(self, task: str) -> float:
        keywords = ["code", "file", "git", "commit", "python", "script",
                     "vscode", "vs code", "review", "debug", "function",
                     "diff", "directory", "folder", "list files"]
        task_lower = task.lower()
        matches = sum(1 for kw in keywords if kw in task_lower)
        return min(0.9, 0.1 + matches * 0.4)

    def execute(self, task: str, context: str = "") -> AgentResult:
        tool_schemas = self._get_relevant_tools()
        plan_result = self.planner.plan_and_select_tools(task, context, tool_schemas)

        if plan_result["type"] == "tools":
            tool_results = self._execute_tool_calls(plan_result["tool_calls"])
            bus = get_message_bus()
            bus.publish("code_action", self.name, {"task": task})

            try:
                response_stream = self.planner.evaluate_result_stream(task, tool_results)
                response = ""
            except Exception:
                response_stream = None
                response = ". ".join(str(tr.get("result", "Done")) for tr in tool_results)

            return AgentResult(success=True, response=response,
                               agent_name=self.name, tool_results=tool_results,
                               response_stream=response_stream)

        return AgentResult(success=True, response=plan_result.get("content", "Done."),
                           agent_name=self.name)


class AutomationAgent(BaseAgent):
    """Specialized agent for system control, app launching, and automation."""

    def __init__(self, tool_manager: ToolManager, memory: MemoryManager):
        super().__init__(
            name="automation",
            description="Handles app launching, system controls, power management, clipboard, terminal.",
            capabilities=["open_application", "set_volume", "set_brightness", "mute_volume",
                           "toggle_wifi", "manage_power", "get_system_status",
                           "clipboard_", "execute_terminal", "run_powershell",
                           "computer_use"],
            tool_manager=tool_manager,
            memory=memory
        )
        self.planner = Planner()

    def can_handle(self, task: str) -> float:
        keywords = ["open", "launch", "volume", "brightness", "mute", "wifi",
                     "shutdown", "restart", "sleep", "lock", "clipboard",
                     "terminal", "command", "powershell", "battery", "cpu", "ram",
                     "system status", "app", "system info", "system information", "system"]
        task_lower = task.lower()
        matches = sum(1 for kw in keywords if kw in task_lower)
        return min(0.9, 0.1 + matches * 0.4)

    def execute(self, task: str, context: str = "") -> AgentResult:
        tool_schemas = self._get_relevant_tools()
        plan_result = self.planner.plan_and_select_tools(task, context, tool_schemas)

        if plan_result["type"] == "tools":
            tool_results = self._execute_tool_calls(plan_result["tool_calls"])
            bus = get_message_bus()
            for tr in tool_results:
                bus.publish("system_action", self.name, {
                    "tool": tr["tool"],
                    "success": tr["verified_success"]
                })

            try:
                response_stream = self.planner.evaluate_result_stream(task, tool_results)
                response = ""
            except Exception:
                response_stream = None
                response = ". ".join(str(tr.get("result", "Done")) for tr in tool_results)

            return AgentResult(success=True, response=response,
                               agent_name=self.name, tool_results=tool_results,
                               response_stream=response_stream)

        return AgentResult(success=True, response=plan_result.get("content", "Done."),
                           agent_name=self.name)


class ReflectionAgent(BaseAgent):
    """
    Agentic self-healing. Invoked when another agent's tool execution fails.
    Analyzes the error, formulates a new plan, and retries the execution.
    """
    def __init__(self, tool_manager: ToolManager, memory: MemoryManager):
        super().__init__(
            name="reflection",
            description="Self-healing agent that fixes tool execution errors.",
            capabilities=[],  # Can use any tool to fix issues
            tool_manager=tool_manager,
            memory=memory
        )
        self.planner = Planner()
        
    def can_handle(self, task: str) -> float:
        return 0.0 # Only invoked manually by Orchestrator
        
    def execute(self, task: str, context: str = "") -> AgentResult:
        tool_schemas = self.tool_manager.get_tool_schemas()
        
        prompt = (
            f"The previous agent failed to complete the task: '{task}'\n\n"
            f"Error details from the failed tool execution:\n{context}\n\n"
            f"Please analyze the error. Adjust the tool arguments, or use a different tool to accomplish the task successfully."
        )
        
        plan_result = self.planner.plan_and_select_tools(prompt, "", tool_schemas)
        
        if plan_result["type"] == "tools":
            tool_results = self._execute_tool_calls(plan_result["tool_calls"])
            
            try:
                response_stream = self.planner.evaluate_result_stream(task, tool_results)
                response = ""
            except Exception:
                response_stream = None
                response = ". ".join(str(tr.get("result", "Done")) for tr in tool_results)

            all_success = all(tr.get("verified_success", False) for tr in tool_results)
            return AgentResult(
                success=all_success,
                response=response,
                agent_name=self.name,
                tool_results=tool_results,
                response_stream=response_stream
            )

        return AgentResult(success=True, response=plan_result.get("content", "Done."),
                           agent_name=self.name)


class Orchestrator:
    """
    Meta-agent that decomposes complex requests into sub-tasks and
    delegates to specialized agents. Supports parallel execution.
    
    Pipeline:
      1. Receive user request
      2. Retrieve memory context
      3. Classify: single-agent vs multi-agent task
      4. Route to best agent(s)
      5. Execute (parallel if multiple)
      6. Combine results
      7. Store in memory
    """

    def __init__(self):
        self.memory = MemoryManager()
        self.tool_manager = ToolManager()
        self.bus = get_message_bus()
        self.executor = ThreadPoolExecutor(max_workers=4)

        # Register specialized agents
        self.agents: List[BaseAgent] = [
            WebAgent(self.tool_manager, self.memory),
            CodingAgent(self.tool_manager, self.memory),
            AutomationAgent(self.tool_manager, self.memory),
            SystemAgent(self.tool_manager, self.memory),  # Fallback — must be last
        ]
        self.reflection_agent = ReflectionAgent(self.tool_manager, self.memory)

        print(f"[Orchestrator] Initialized with {len(self.agents)} agents: "
              f"{[a.name for a in self.agents]}")

    def process_command(self, text: str, conversation_context: str = "") -> dict:
        """
        Main entry point. Processes a user command through the multi-agent pipeline.
        Returns a dict compatible with the existing OSKernel interface.
        
        Args:
            text: The user's command text.
            conversation_context: Optional conversation history for multi-turn context.
        """
        response_dict = {
            "success": True,
            "response": "",
            "action": ""
        }

        try:
            # 1. Retrieve memory context
            try:
                past_context = self.memory.retrieve_relevant_conversation(text, n_results=3)
                context_str = "\n".join(past_context)
            except Exception:
                context_str = ""

            # Add conversation context (from ConversationManager)
            if conversation_context:
                context_str = conversation_context + "\n\n" + context_str

            # Add message bus context (what other agents have been doing)
            bus_context = self.bus.get_context_summary()
            if bus_context:
                context_str += f"\n\nRecent agent activity:\n{bus_context}"

            # 2. Check if this is a multi-agent task
            subtasks = self._decompose_if_needed(text)

            if len(subtasks) > 1:
                # Multi-agent: execute subtasks in parallel
                result = self._execute_parallel(subtasks, context_str)
            else:
                # Single task: route to best agent
                result = self._route_single(text, context_str)

            response_dict["success"] = result.success
            response_dict["response"] = result.response
            response_dict["response_stream"] = getattr(result, "response_stream", None)
            response_dict["action"] = f"[{result.agent_name}] {result.metadata.get('action', 'Completed')}"

            # 3. Store in memory
            try:
                self.memory.add_conversation("user", text)
                # We can't immediately store the full response if it's streaming.
                # The VoicePipeline will have to handle storing the fully accumulated response.
                if not response_dict["response_stream"]:
                    self.memory.add_conversation("jarvis", response_dict["response"])
            except Exception:
                pass

        except Exception as e:
            error_trace = traceback.format_exc()
            print(f"[Orchestrator] Pipeline error: {error_trace}")
            response_dict["success"] = False
            response_dict["response"] = f"Pipeline error: {str(e)}"
            response_dict["action"] = "Error"
            response_dict["response_stream"] = None

        return response_dict

    def _route_single(self, task: str, context: str) -> AgentResult:
        """Route a single task to the best agent. Includes auto-retry via ReflectionAgent."""
        # Score each agent
        scores = [(agent, agent.can_handle(task)) for agent in self.agents]
        scores.sort(key=lambda x: x[1], reverse=True)

        best_agent, best_score = scores[0]
        print(f"[Orchestrator] Routing to '{best_agent.name}' (score={best_score:.2f})")

        result = best_agent.execute(task, context)
        result.metadata["action"] = f"Handled by {best_agent.name}"

        # Agentic Self-Healing
        if not result.success and result.tool_results:
            print(f"[Orchestrator] Execution failed by {best_agent.name}. Invoking ReflectionAgent for self-healing.")
            # Gather errors
            errors = []
            for tr in result.tool_results:
                if not tr.get("verified_success", True):
                    errors.append(f"Tool '{tr.get('tool')}' failed with result: {tr.get('result')}")
            
            if errors:
                error_context = "\n".join(errors)
                retry_result = self.reflection_agent.execute(task, error_context)
                
                if retry_result.success:
                    print(f"[Orchestrator] ReflectionAgent successfully healed the execution.")
                    retry_result.metadata["action"] = f"Healed by reflection (original agent: {best_agent.name})"
                    return retry_result
                else:
                    print(f"[Orchestrator] ReflectionAgent failed to heal.")
                    # Keep the retry_result so the user sees the final attempt's error
                    retry_result.metadata["action"] = f"Failed after reflection (original agent: {best_agent.name})"
                    return retry_result

        return result

    def _decompose_if_needed(self, text: str) -> List[str]:
        """
        Check if the request contains multiple independent tasks.
        Uses simple heuristics first, then LLM for complex cases.
        """
        # Heuristic: split on "and then", "also", "after that"
        separators = [" and then ", " then ", " also ", " after that "]
        for sep in separators:
            if sep in text.lower():
                parts = re.split(re.escape(sep), text, flags=re.IGNORECASE)
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) > 1:
                    print(f"[Orchestrator] Decomposed into {len(parts)} subtasks: {parts}")
                    return parts

        return [text]

    def _execute_parallel(self, subtasks: List[str], context: str) -> AgentResult:
        """Execute multiple subtasks in parallel using ThreadPoolExecutor."""
        futures = {}
        for subtask in subtasks:
            # Route each subtask to its best agent
            scores = [(agent, agent.can_handle(subtask)) for agent in self.agents]
            scores.sort(key=lambda x: x[1], reverse=True)
            best_agent = scores[0][0]

            future = self.executor.submit(best_agent.execute, subtask, context)
            futures[future] = (subtask, best_agent.name)

        # Collect results
        all_results = []
        all_responses = []
        all_success = True

        for future in as_completed(futures):
            subtask, agent_name = futures[future]
            try:
                result = future.result(timeout=120)
                all_results.append(result)
                all_responses.append(result.response)
                if not result.success:
                    all_success = False
            except Exception as e:
                all_responses.append(f"Failed: {subtask} ({e})")
                all_success = False

        combined_response = " ".join(all_responses)
        return AgentResult(
            success=all_success,
            response=combined_response,
            agent_name="orchestrator",
            metadata={"action": f"Executed {len(subtasks)} subtasks in parallel"}
        )
