"""
J.A.R.V.I.S. ReAct Agentic Loop Engine
═══════════════════════════════════════
Implements autonomous multi-step reasoning using native LLM function calling:
Reason → Act (Tool Call) → Observe (Result) → Re-plan / Finish.

Uses llm_chat() with tool schemas for structured tool invocation instead of
brittle JSON text parsing. This is the gold-standard agentic pattern.
"""

import os
import json
import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from core.agentic_tools import get_agentic_tools, AgenticToolRegistry
from core.llm_provider import llm_chat
from core.message_bus import get_message_bus
from core.verification_agent import FAILURE_KEYWORDS, SUCCESS_KEYWORDS

logger = logging.getLogger("jarvis.agentic_loop")


@dataclass
class StepResult:
    thought: str
    tool_name: str
    tool_args: Dict[str, Any]
    observation: str
    # Verified outcome of this step: True = succeeded, False = failed,
    # None = unclear. Never claim success for a step that isn't verified.
    succeeded: Optional[bool] = None


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

    # How many times to retry a transient LLM/provider failure before giving up.
    MAX_LLM_RETRIES = 3

    # Substrings in a tool name that mark it as potentially destructive/irreversible.
    # Catches high-risk tools that were never given an explicit is_dangerous flag.
    _DANGEROUS_NAME_HINTS = (
        "delete", "remove", "kill", "uninstall", "format", "wipe", "erase",
        "shutdown", "reboot", "restart", "send", "email", "message", "whatsapp",
        "post", "publish", "buy", "purchase", "pay", "transfer", "commit", "push",
        "terminal", "powershell", "shell", "exec", "run_python", "write_code",
    )

    def __init__(self, max_iterations: int = 10,
                 registry: Optional[AgenticToolRegistry] = None,
                 autonomy: Optional[str] = None):
        self.max_iterations = max_iterations
        self.registry: AgenticToolRegistry = registry or get_agentic_tools()
        self.bus = get_message_bus()
        # Autonomy policy for destructive tools:
        #   "guarded" (default) — refuse dangerous tools and ask the user to confirm
        #   "full"              — execute everything, no confirmation
        self.autonomy = (autonomy or os.environ.get("JARVIS_AGENTIC_AUTONOMY", "guarded")).lower()
        # LLM routing for the agentic brain (resolved live each run so it adapts
        # when Claude runs out of credits mid-session). JARVIS_AGENTIC_PROVIDER:
        #   "auto" (default) — Claude if it has credits, else Groq, else free tier
        #   "claude"         — Claude (falls back to Groq if Claude is unavailable)
        #   "groq"           — Groq
        #   "free"           — never prefer a paid/premium provider

    @staticmethod
    def _resolve_llm_preference() -> Optional[str]:
        """Resolve the preferred provider for THIS run (state-aware)."""
        try:
            from core.llm_provider import agentic_preference
            return agentic_preference()
        except Exception:
            return None

    def _is_dangerous(self, tool_name: str) -> bool:
        """Decide whether a tool needs explicit confirmation before running.

        Combines the declared safety flags (``is_dangerous`` /
        ``requires_confirmation`` from the @tool decorator) with a name-based
        heuristic, since most destructive tools were never flagged.
        """
        meta = self.registry.get_meta(tool_name) if hasattr(self.registry, "get_meta") else {}
        if meta.get("is_dangerous") or meta.get("requires_confirmation"):
            return True
        low = tool_name.lower()
        return any(hint in low for hint in self._DANGEROUS_NAME_HINTS)

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

        # A fresh task clears any prior emergency stop so it isn't killed by a
        # stale flag; the loop then re-checks the flag before every step.
        from core.control import get_control_plane
        control = get_control_plane()
        control.clear_stop()

        # Resolve which LLM to prefer for this run (adapts if Claude is out of credits).
        prefer_llm = self._resolve_llm_preference()

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
            # Emergency stop: halt cleanly between steps if the user hit stop.
            if control.is_stopped():
                logger.warning("[ReActLoop] Emergency stop — halting workflow.")
                self._notify_ui(goal, "Stopped", 100)
                return AgenticResult(
                    success=False,
                    response="Stopped, sir. " + self._deterministic_summary(scratchpad),
                    steps=scratchpad,
                    total_time=time.time() - start_time,
                )

            percent = int((iteration / self.max_iterations) * 85)
            self._notify_ui(goal, f"Step {iteration}: reasoning...", percent)

            # Call the LLM, retrying transient provider failures (rate limits,
            # brief outages) with exponential backoff. A provider failure is NOT
            # a finished answer, so we must not treat it as task completion.
            result = None
            for attempt in range(self.MAX_LLM_RETRIES + 1):
                try:
                    result = llm_chat(messages, tools=tool_schemas, temperature=0.0,
                                      timeout=120, prefer=prefer_llm)
                except Exception as e:
                    logger.warning("[ReActLoop] LLM call raised (attempt %d): %s", attempt + 1, e)
                    result = None
                if result is not None and not result.get("provider_error"):
                    break
                if attempt < self.MAX_LLM_RETRIES:
                    wait = min(2 ** attempt, 8)
                    self._notify_ui(goal, f"AI is busy — retrying in {wait}s…", percent)
                    logger.info("[ReActLoop] Provider busy; backing off %ds (attempt %d/%d)",
                                wait, attempt + 1, self.MAX_LLM_RETRIES)
                    time.sleep(wait)

            if result is None or result.get("provider_error"):
                # Model unreachable after retries — fail honestly, preserving
                # whatever was accomplished. Do NOT call the LLM for a summary
                # here (it would fail too); use a deterministic one.
                logger.error("[ReActLoop] LLM retries exhausted; aborting workflow.")
                self._notify_ui(goal, "AI unavailable", 100)
                return AgenticResult(
                    success=False,
                    response=(
                        "I lost the connection to the AI model partway through "
                        "(most likely a rate limit on the free tier). "
                        + self._deterministic_summary(scratchpad)
                        + " Adding a GROQ_API_KEY would give more headroom, sir."
                    ),
                    steps=scratchpad,
                    total_time=time.time() - start_time,
                )

            # Check if LLM returned tool calls
            tool_calls = result.get("tool_calls", [])
            content = (result.get("content") or "").strip()

            if not tool_calls:
                # No tool calls = LLM thinks the task is done, returned a text response
                final_response = content or self._synthesize_summary(goal, scratchpad)
                self._notify_ui(goal, "Done", 100)
                logger.info("[ReActLoop] Finished at iteration %d with text response", iteration)
                return AgenticResult(
                    success=self._overall_success(scratchpad),
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
                            success=bool(scratchpad) and self._overall_success(scratchpad),
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

                # ── Safety gate: refuse destructive tools unless autonomy=full ──
                if self.autonomy != "full" and self._is_dangerous(tool_name):
                    logger.warning("[ReActLoop] Blocked dangerous tool '%s' (autonomy=%s).",
                                   tool_name, self.autonomy)
                    observation = (
                        f"BLOCKED: '{tool_name}' is a potentially destructive/irreversible action "
                        f"and requires the user's explicit confirmation. It was NOT executed. "
                        f"Do not retry it. Continue with any safe steps you can, then finish with a "
                        f"spoken summary that clearly asks the user to confirm this specific action "
                        f"(mention the tool and what it would do) before it can proceed."
                    )
                    scratchpad.append(StepResult(
                        thought=content or f"Blocked {tool_name}",
                        tool_name=tool_name,
                        tool_args=tool_args,
                        observation=observation,
                        succeeded=False,  # blocked means it did NOT happen
                    ))
                    messages.append({"role": "assistant",
                                     "content": f"Attempted {tool_name}({json.dumps(tool_args, default=str)})"})
                    messages.append({"role": "user", "content": observation})
                    try:
                        self.bus.publish("agentic_blocked", sender="agentic_loop",
                                         payload={"tool": tool_name, "args": str(tool_args)})
                    except Exception:
                        pass
                    continue

                logger.info("[ReActLoop] Iteration %d: Calling tool '%s' with args: %s",
                            iteration, tool_name, tool_args)
                self._notify_ui(goal, f"Executing: {tool_name}", min(percent + 5, 95))

                # Execute the tool
                observation = self.registry.execute(tool_name, tool_args)
                succeeded = self._verify_observation(observation)
                logger.info("[ReActLoop] Iteration %d: Tool '%s' returned (verified=%s): %s",
                            iteration, tool_name, succeeded, str(observation)[:200])

                # Record step
                scratchpad.append(StepResult(
                    thought=content or f"Calling {tool_name}",
                    tool_name=tool_name,
                    tool_args=tool_args,
                    observation=observation,
                    succeeded=succeeded,
                ))

                # Append tool call and result to conversation for multi-turn.
                # Failures are labelled explicitly so the model reliably notices
                # and adapts instead of assuming the step worked.
                verdict = {True: "SUCCEEDED", False: "FAILED", None: "UNCLEAR"}[succeeded]
                messages.append({"role": "assistant",
                                 "content": f"Called {tool_name}({json.dumps(tool_args, default=str)})"})
                messages.append({"role": "user",
                                 "content": f"Tool '{tool_name}' {verdict}. It returned:\n"
                                            f"{str(observation)[:1500]}"})

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
            success=bool(scratchpad) and self._overall_success(scratchpad),
            response=self._synthesize_summary(goal, scratchpad),
            steps=scratchpad,
            total_time=time.time() - start_time
        )

    @staticmethod
    def _verify_observation(observation: Any) -> Optional[bool]:
        """Judge whether a tool result reports success, failure, or is unclear.

        Returns True (verified success), False (verified failure) or None
        (unclear — claim neither). Deliberately heuristic-only: the loop
        already makes one LLM call per iteration and the free tiers are
        rate-limited, so verification must not add a second call per step.
        """
        text = str(observation).strip()
        if not text:
            return None
        lowered = text.lower()

        # ToolManager returns {"error": ...} and the registry returns
        # "Error ..." strings when a tool raises.
        if lowered.startswith(("{'error'", '{"error"')):
            return False
        if "traceback (most recent call last)" in lowered:
            return False

        # Earliest signal wins: a result that *starts* by reporting success is a
        # success even if its payload quotes failure words later (e.g. sending a
        # message whose body says "I could not make it"), and vice-versa.
        first_fail = min((lowered.find(k) for k in FAILURE_KEYWORDS if k in lowered),
                         default=-1)
        first_ok = min((lowered.find(k) for k in SUCCESS_KEYWORDS if k in lowered),
                       default=-1)

        if first_fail == -1 and first_ok == -1:
            return None
        if first_fail == -1:
            return True
        if first_ok == -1:
            return False
        return first_ok < first_fail

    @staticmethod
    def _overall_success(scratchpad: List[StepResult]) -> bool:
        """Whether the run as a whole should be reported as successful.

        A ReAct run often includes a failed step that a later step recovers
        from, so one failure is not fatal. But if the final action failed, or
        every action failed, the goal was not achieved — say so.
        """
        real = [s for s in scratchpad if s.tool_name != "ERROR"]
        if not real:
            return True  # nothing was attempted, so there's no failure to report
        if real[-1].succeeded is False:
            return False
        if all(s.succeeded is False for s in real):
            return False
        return True

    @staticmethod
    def _deterministic_summary(scratchpad: List[StepResult]) -> str:
        """Summarize actions taken WITHOUT calling the LLM (used when it's down)."""
        steps = [s for s in scratchpad if s.tool_name != "ERROR"]
        if not steps:
            return "I hadn't completed any actions yet."
        ran = "So far I ran: " + ", ".join(s.tool_name for s in steps[-6:]) + "."
        failed = [s.tool_name for s in steps if s.succeeded is False]
        if failed:
            ran += " These failed: " + ", ".join(dict.fromkeys(failed)) + "."
        return ran

    def _synthesize_summary(self, goal: str, scratchpad: List[StepResult]) -> str:
        """Produce a concise, natural spoken summary of what was accomplished.

        Called when the loop ends without the model volunteering a final
        message (e.g. max iterations or a loop-guard abort). Falls back to a
        deterministic summary if the LLM call fails.
        """
        if not scratchpad:
            return "I wasn't able to take any action on that, sir."

        marker = {True: "SUCCEEDED", False: "FAILED", None: "UNCLEAR"}
        steps_text = "\n".join(
            f"- {s.tool_name} [{marker[s.succeeded]}]: {str(s.observation)[:150]}"
            for s in scratchpad[-8:]
        )
        try:
            summary = llm_chat(
                [
                    {"role": "system", "content":
                        "You are J.A.R.V.I.S. Summarize the outcome of the actions you took in "
                        "1-2 short spoken sentences for the user. Be concrete about what got done. "
                        "Each action is tagged SUCCEEDED, FAILED or UNCLEAR. Never claim something "
                        "worked if it is tagged FAILED — say plainly what failed. "
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
        failed = [s.tool_name for s in scratchpad if s.succeeded is False]
        if failed:
            return (f"I ran {len(scratchpad)} step(s), but these failed: "
                    f"{', '.join(dict.fromkeys(failed))}. "
                    f"Last result: {str(last.observation)[:200]}")
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
            "6. Be efficient — don't take unnecessary steps. Prefer the most direct path to the goal.\n"
            "7. To BUILD or CREATE anything real (a website, app, game, script, tool, automation, "
            "or multi-file project), call `build_with_claude(request, project_name)`. It uses Claude "
            "as the build engine and writes actual working files. Pass a detailed 'request' capturing "
            "everything the user asked for. This is the primary way to build.\n"
            "8. ONLY for a trivial single-file widget you can fully write yourself in one short HTML "
            "document (inline CSS + JS), you may instead call `build_web_app(name, html)`. When in "
            "doubt, prefer `build_with_claude`. Never use bolt, lovable, scaffold, npm, or dev-server "
            "tools — they are unreliable and not wanted.\n"
            "9. Never claim success you haven't verified. Only report a task done when a tool "
            "result confirms it; if a result is an error, say so plainly.\n"
            + (
                "7. SAFETY: destructive or irreversible actions (deleting, sending messages/email, "
                "killing processes, running shell commands, purchases) are guarded. If one is blocked, "
                "do NOT retry it — finish and clearly ask the user to confirm that specific action.\n"
                if self.autonomy != "full" else ""
            )
            + f"\nCONTEXT (memory, screen state, conversation):\n{context or 'None'}\n"
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
