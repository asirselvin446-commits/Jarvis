"""
J.A.R.V.I.S. ReAct Agentic Loop Engine
═══════════════════════════════════════
Implements autonomous multi-step reasoning using native LLM function calling:
Reason → Act (Tool Call) → Observe (Result) → Re-plan / Finish.

Uses llm_chat() with tool schemas for structured tool invocation instead of
brittle JSON text parsing. This is the gold-standard agentic pattern.
"""

import json
import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from core.agentic_tools import get_agentic_tools, AgenticToolRegistry
from core.llm_provider import llm_chat
from core.message_bus import get_message_bus

logger = logging.getLogger("jarvis.agentic_loop")


@dataclass
class StepResult:
    thought: str
    tool_name: str
    tool_args: Dict[str, Any]
    observation: str


@dataclass
class AgenticResult:
    success: bool
    response: str
    steps: List[StepResult]
    total_time: float


class ReActLoop:
    """
    ReAct (Reason + Act) Loop using native LLM function calling.
    Executes complex, open-ended multi-step instructions by iteratively
    calling tools and feeding results back to the LLM until the goal
    is fully achieved.
    """

    # Break out if the same (tool, args) pair is attempted this many times.
    MAX_REPEAT = 3

    def __init__(self, max_iterations: int = 10, registry: Optional[AgenticToolRegistry] = None):
        self.max_iterations = max_iterations
        self.registry: AgenticToolRegistry = registry or get_agentic_tools()
        self.bus = get_message_bus()

    def run(self, goal: str, context: str = "") -> AgenticResult:
        """
        Main execution loop for an open-ended agentic goal.
        Uses native function calling for reliable tool invocation.

        Reason → Act → Observe → Re-plan, iterating until the LLM decides the
        goal is met (returns text with no tool call) or the iteration budget is
        exhausted. Guards against infinite loops by detecting repeated calls.
        """
        start_time = time.time()
        logger.info("[ReActLoop] Starting agentic workflow for goal: '%s'", goal)
        self._notify_ui(goal, "Planning...", 10)

        scratchpad: List[StepResult] = []
        # Fingerprint counter for loop detection: "tool_name(args_json)" -> count
        call_counts: Dict[str, int] = {}

        # Build conversation messages for multi-turn function calling
        system_prompt = self._build_system_prompt(goal, context)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": goal}
        ]

        tool_schemas = self.registry.get_tool_schemas_for_llm()

        for iteration in range(1, self.max_iterations + 1):
            percent = int((iteration / self.max_iterations) * 85)
            self._notify_ui(goal, f"Step {iteration}: reasoning...", percent)

            try:
                # Call LLM with native function calling
                result = llm_chat(messages, tools=tool_schemas, temperature=0.0, timeout=60)
            except Exception as e:
                logger.error("[ReActLoop] Iteration %d LLM call failed: %s", iteration, e)
                scratchpad.append(StepResult(
                    thought=f"LLM call failed: {e}",
                    tool_name="ERROR",
                    tool_args={},
                    observation=str(e)
                ))
                time.sleep(1.0)
                continue

            # Check if LLM returned tool calls
            tool_calls = result.get("tool_calls", [])
            content = (result.get("content") or "").strip()

            if not tool_calls:
                # No tool calls = LLM thinks the task is done, returned a text response
                final_response = content or self._synthesize_summary(goal, scratchpad)
                self._notify_ui(goal, "Done", 100)
                logger.info("[ReActLoop] Finished at iteration %d with text response", iteration)
                return AgenticResult(
                    success=True,
                    response=final_response,
                    steps=scratchpad,
                    total_time=time.time() - start_time
                )

            # Execute each tool call the model requested this turn
            for tc in tool_calls:
                func_info = tc.get("function", {})
                tool_name = func_info.get("name", "unknown")
                tool_args = func_info.get("arguments", {})
                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError:
                        tool_args = {}

                # ── Loop guard: detect the model repeating an identical action ──
                fingerprint = f"{tool_name}({json.dumps(tool_args, sort_keys=True, default=str)})"
                call_counts[fingerprint] = call_counts.get(fingerprint, 0) + 1
                repeats = call_counts[fingerprint]
                if repeats > self.MAX_REPEAT:
                    logger.warning("[ReActLoop] Loop guard: '%s' requested %d times.",
                                   tool_name, repeats)
                    # If the model already ignored one nudge, stop wasting turns.
                    if repeats > self.MAX_REPEAT + 1:
                        logger.warning("[ReActLoop] Nudge ignored — ending workflow.")
                        return AgenticResult(
                            success=bool(scratchpad),
                            response=self._synthesize_summary(goal, scratchpad),
                            steps=scratchpad,
                            total_time=time.time() - start_time,
                        )
                    messages.append({
                        "role": "user",
                        "content": (
                            f"You have already called {tool_name} with the same arguments "
                            f"{self.MAX_REPEAT} times without progress. Stop repeating it. "
                            "Either try a different approach or, if the goal is done or blocked, "
                            "give a short spoken summary now with no further tool calls."
                        )
                    })
                    break

                logger.info("[ReActLoop] Iteration %d: Calling tool '%s' with args: %s",
                            iteration, tool_name, tool_args)
                self._notify_ui(goal, f"Executing: {tool_name}", min(percent + 5, 95))

                # Execute the tool
                observation = self.registry.execute(tool_name, tool_args)
                logger.info("[ReActLoop] Iteration %d: Tool '%s' returned: %s",
                            iteration, tool_name, str(observation)[:200])

                # Record step
                scratchpad.append(StepResult(
                    thought=content or f"Calling {tool_name}",
                    tool_name=tool_name,
                    tool_args=tool_args,
                    observation=observation
                ))

                # Append tool call and result to conversation for multi-turn
                messages.append({"role": "assistant",
                                 "content": f"Called {tool_name}({json.dumps(tool_args, default=str)})"})
                messages.append({"role": "user",
                                 "content": f"Tool '{tool_name}' returned:\n{str(observation)[:1500]}"})

                # Publish tool execution event for UI updates
                try:
                    self.bus.publish(
                        "tool_executed",
                        sender="agentic_loop",
                        payload={"tool": tool_name, "args": str(tool_args),
                                 "observation": str(observation)[:100]}
                    )
                except Exception:
                    pass

        # Max iterations reached — synthesize a clean summary of what happened.
        self._notify_ui(goal, "Wrapping up", 100)
        logger.info("[ReActLoop] Reached max iterations (%d)", self.max_iterations)
        return AgenticResult(
            success=bool(scratchpad),
            response=self._synthesize_summary(goal, scratchpad),
            steps=scratchpad,
            total_time=time.time() - start_time
        )

    def _synthesize_summary(self, goal: str, scratchpad: List[StepResult]) -> str:
        """Produce a concise, natural spoken summary of what was accomplished.

        Called when the loop ends without the model volunteering a final
        message (e.g. max iterations or a loop-guard abort). Falls back to a
        deterministic summary if the LLM call fails.
        """
        if not scratchpad:
            return "I wasn't able to take any action on that, sir."

        steps_text = "\n".join(
            f"- {s.tool_name}: {str(s.observation)[:150]}" for s in scratchpad[-8:]
        )
        try:
            summary = llm_chat(
                [
                    {"role": "system", "content":
                        "You are J.A.R.V.I.S. Summarize the outcome of the actions you took in "
                        "1-2 short spoken sentences for the user. Be concrete about what got done. "
                        "No tool calls, no markdown."},
                    {"role": "user", "content":
                        f"Goal: {goal}\n\nActions taken:\n{steps_text}\n\nGive the spoken summary."},
                ],
                temperature=0.2, timeout=30,
            )
            text = (summary.get("content") or "").strip()
            if text:
                return text
        except Exception as e:
            logger.debug("[ReActLoop] Summary synthesis failed: %s", e)

        last = scratchpad[-1]
        return f"I completed {len(scratchpad)} step(s). Last result: {str(last.observation)[:200]}"

    def _build_system_prompt(self, goal: str, context: str) -> str:
        """Build the system prompt for the agentic loop."""
        return (
            "You are J.A.R.V.I.S., an autonomous AI agent executing a task on the user's Windows PC.\n"
            "You have native function-calling tools available. Use them to actually DO things.\n\n"
            "RULES:\n"
            "1. You MUST call tools to accomplish the goal. Do NOT describe actions — execute them.\n"
            "2. Work step by step. After each tool result, decide the next action based on what "
            "actually happened, not what you assumed.\n"
            "3. When the goal is FULLY accomplished, reply with a brief spoken summary and NO tool call.\n"
            "4. If a tool fails or returns an error, adapt: fix the arguments or try a different tool. "
            "Do not repeat the exact same failing call.\n"
            "5. For GUI tasks with no dedicated tool, use `computer_use(goal=\"...\")` as a fallback.\n"
            "6. Be efficient — don't take unnecessary steps. Prefer the most direct path to the goal.\n\n"
            f"CONTEXT (memory, screen state, conversation):\n{context or 'None'}\n"
        )

    def _notify_ui(self, task: str, status: str, percent: int):
        """Notify the web UI execution progress panel via MessageBus."""
        try:
            self.bus.publish(
                "task_execute_automation",
                sender="agentic_loop",
                payload={"task": task, "status": status, "percent": percent}
            )
        except Exception:
            pass
