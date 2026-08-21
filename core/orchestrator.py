"""
J.A.R.V.I.S. Orchestrator
═══════════════════════════
Unified agent that processes all user commands through a single
Planner → Tool Execution → Response pipeline.

Architecture:
  1. Receive user request + conversation context
  2. Retrieve memory context (conversations, learnings, knowledge graph)
  3. Pass to Planner (which handles tool selection via LLM function calling)
  4. Execute tools, verify results
  5. Stream response back to the user
  6. Store in memory

Previous design had 4 specialized agents (Web, Coding, Automation, System)
with keyword-based routing. This was collapsed into a single unified pipeline
because the LLM's native function calling already selects the right tools —
keyword routing just added latency and misrouting.
"""

import os
import json
import re
import traceback
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

from core.planner import Planner
from core.memory import get_memory_manager
from core.tool_manager import ToolManager
from core.verification_agent import VerificationAgent
from core.message_bus import get_message_bus
from core.security import is_dangerous_tool

logger = logging.getLogger("jarvis.orchestrator")

# Lazy imports for new futuristic modules
def _get_self_healer():
    try:
        from core.self_healer import get_self_healer
        return get_self_healer()
    except Exception:
        return None

def _get_habit_learner():
    try:
        from core.habit_engine import get_habit_learner
        return get_habit_learner()
    except Exception:
        return None


class Orchestrator:
    """
    Unified command processing pipeline.
    All commands go through: Memory → Planner (LLM + Tools) → Response.
    """

    def __init__(self):
        self.memory = get_memory_manager()
        self.tool_manager = ToolManager()
        self.planner = Planner()
        self.verification = VerificationAgent()
        self.bus = get_message_bus()
        self.executor = ThreadPoolExecutor(max_workers=4)

        # Agentic (ReAct) brain — lazily created, reuses this ToolManager so it
        # can chain any of the registered tools across multiple adaptive steps.
        self._agentic_loop = None
        # Autonomous multi-step reasoning for open-ended goals. On by default;
        # set JARVIS_AGENTIC_MODE=0 to force the classic single-shot pipeline.
        self.agentic_enabled = os.environ.get("JARVIS_AGENTIC_MODE", "1") != "0"

        # Autonomy policy for destructive tools on the single-shot path. Shares
        # the same env var as the agentic loop so both paths obey one setting:
        #   "guarded" (default) — hold dangerous tools for spoken confirmation
        #   "full"              — execute everything, no confirmation
        self.autonomy = os.environ.get("JARVIS_AGENTIC_AUTONOMY", "guarded").lower()
        # A dangerous tool call held back awaiting the user's "yes".
        self._pending_action: Optional[dict] = None

        tool_names = list(self.tool_manager.tools.keys())
        print(f"[Orchestrator] Initialized with {len(tool_names)} tools: {tool_names}")

    def _get_agentic_loop(self):
        """Lazily build the ReAct agentic loop, sharing this Orchestrator's ToolManager."""
        if self._agentic_loop is None:
            from core.agentic_loop import ReActLoop
            from core.agentic_tools import get_agentic_tools
            registry = get_agentic_tools(tool_manager=self.tool_manager)
            self._agentic_loop = ReActLoop(max_iterations=12, registry=registry)
            logger.info("[Orchestrator] Agentic ReAct brain initialized.")
        return self._agentic_loop

    def process_command(self, text: str, conversation_context: str = "") -> dict:
        """
        Main entry point. Processes a user command through the unified pipeline.
        Returns a dict compatible with the VoicePipeline interface.

        Args:
            text: The user's command text.
            conversation_context: Optional conversation history for multi-turn context.
        """
        response_dict = {
            "success": True,
            "response": "",
            "action": "",
            "response_stream": None
        }

        # Feed command to Habit Engine for pattern learning
        habit = _get_habit_learner()
        if habit:
            try:
                habit.observe_command(text)
            except Exception:
                pass

        # Emotional sentiment analysis
        try:
            from core.emotion_engine import get_emotion_engine
            get_emotion_engine().analyze(text)
        except Exception:
            pass

        try:
            # 0a. A pending dangerous action takes priority: a bare "yes"/"no"
            #     here is answering the confirmation prompt, not a new command.
            confirmed = self._resolve_pending_confirmation(text)
            if confirmed:
                self._store_and_learn(text, confirmed)
                return confirmed

            # 0b. Fast Path for instant intent execution (Bypass LLM)
            fast_action = self._check_fast_path(text)
            if fast_action:
                try:
                    self.memory.add_conversation("user", text)
                    self.memory.add_conversation("jarvis", fast_action.get("response", "Done."))
                except Exception:
                    pass
                return {
                    "success": fast_action.get("success", True),
                    "response": fast_action.get("response", "Done."),
                    "action": fast_action.get("action", "FastPath"),
                    "response_stream": None
                }

            # 1. Build memory context
            context_str = self._build_context(text, conversation_context)

            # 2. Open-ended / multi-step goal → adaptive agentic ReAct loop.
            #    This is what lets Jarvis "do whatever I say": it plans, acts,
            #    observes the real result, and re-plans until the goal is met.
            if self._is_agentic_goal(text):
                result = self._execute_agentic(text, context_str)
                response_dict.update(result)
                self._store_and_learn(text, response_dict)
                return response_dict

            # 3. Otherwise, classic fast path: single-shot or naive decomposition.
            subtasks = self._decompose_if_needed(text)

            if len(subtasks) > 1:
                # Multi-step: sequential or parallel execution
                if getattr(self, '_last_decomposition_mode', 'parallel') == 'sequential':
                    result = self._execute_sequential(subtasks, context_str)
                else:
                    result = self._execute_parallel(subtasks, context_str)
                response_dict["success"] = result["success"]
                response_dict["response"] = result["response"]
                response_dict["response_stream"] = result.get("response_stream")
                response_dict["action"] = result.get("action", "Multi-step completed")
            else:
                # Single task: direct to planner
                result = self._execute_single(text, context_str)
                response_dict.update(result)

            # Store in memory + background knowledge extraction.
            self._store_and_learn(text, response_dict)

        except Exception as e:
            error_trace = traceback.format_exc()
            logger.error("[Orchestrator] Pipeline error: %s", error_trace)
            response_dict["success"] = False
            response_dict["response"] = f"Pipeline error: {str(e)}"
            response_dict["action"] = "Error"
            response_dict["response_stream"] = None

        return response_dict

    def _store_and_learn(self, text: str, response_dict: dict) -> None:
        """Persist the exchange to memory and kick off background knowledge extraction."""
        try:
            self.memory.add_conversation("user", text)
            if not response_dict.get("response_stream"):
                self.memory.add_conversation("jarvis", response_dict.get("response", ""))
        except Exception:
            pass

        try:
            response_for_extract = response_dict.get("response", "")
            threading.Thread(
                target=self._extract_knowledge,
                args=(text, response_for_extract),
                daemon=True
            ).start()
        except Exception:
            pass

    def _execute_single(self, text: str, context_str: str) -> dict:
        """Execute a single command through the Planner pipeline."""
        tool_schemas = self.tool_manager.get_tool_schemas()
        plan_result = self.planner.plan_and_select_tools(text, context_str, tool_schemas)

        if plan_result["type"] == "tools":
            # Execute tool calls
            tool_calls = plan_result["tool_calls"]

            # If planner already executed tools (multi-turn), use those results
            if "tool_results" in plan_result and plan_result["tool_results"]:
                tool_results = plan_result["tool_results"]
            else:
                tool_results = self._execute_tool_calls(tool_calls)

            # Publish events
            for tr in tool_results:
                self.bus.publish("tool_executed", "orchestrator", {
                    "tool": tr.get("tool", "unknown"),
                    "success": tr.get("verified_success", True)
                })

            # Generate response via streaming
            try:
                response_stream = self.planner.evaluate_result_stream(text, tool_results)
                return {
                    "success": all(tr.get("verified_success", True) for tr in tool_results),
                    "response": "",
                    "response_stream": response_stream,
                    "action": f"Executed {len(tool_results)} tool(s)"
                }
            except Exception:
                response = ". ".join(str(tr.get("result", "Done")) for tr in tool_results)
                return {
                    "success": True,
                    "response": response,
                    "response_stream": None,
                    "action": f"Executed {len(tool_results)} tool(s)"
                }

        elif plan_result["type"] == "response":
            return {
                "success": True,
                "response": plan_result["content"],
                "response_stream": None,
                "action": "Direct response"
            }
        else:
            return {
                "success": False,
                "response": plan_result.get("content", "I couldn't process that."),
                "response_stream": None,
                "action": "Error"
            }

    def _execute_tool_calls(self, tool_calls: List[dict]) -> List[dict]:
        """Execute a list of tool calls, verify results, and self-heal on failure."""
        results = []
        for tc in tool_calls:
            try:
                func_info = tc.get("function", {})
                tool_name = func_info.get("name", "")
                args = func_info.get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args)

                # ── Safety gate: hold destructive tools for confirmation ──
                # The @tool safety flags were previously enforced only in the
                # agentic loop, so this path ran flagged tools unchecked.
                if self._should_confirm(tool_name):
                    self._pending_action = {"tool": tool_name, "args": args}
                    logger.warning("[Orchestrator] Holding dangerous tool '%s' for confirmation.", tool_name)
                    self.bus.publish("action_pending_confirmation", "orchestrator",
                                     {"tool": tool_name, "args": str(args)})
                    results.append({
                        "tool": tool_name,
                        "arguments": args,
                        "result": (
                            f"BLOCKED: '{tool_name}' is potentially destructive and was NOT executed. "
                            f"Tell the user plainly what this action would do and ask them to confirm "
                            f"with 'yes' before it can proceed."
                        ),
                        "verified_success": False,
                        "pending_confirmation": True,
                    })
                    continue

                result = self.tool_manager.execute_tool(tool_name, args)
                success = self.verification.verify(tool_name, str(result))

                if not success:
                    # ── Self-Healing Feedback Loop ─────────────────────
                    logger.warning(f"[SelfHeal] Tool '{tool_name}' failed verification. Attempting self-repair...")
                    healed_result = self._attempt_self_heal(tool_name, args, result)
                    if healed_result is not None:
                        result = healed_result
                        success = True
                        logger.info(f"[SelfHeal] Successfully healed '{tool_name}'.")
                    else:
                        # Store the failure in learning memory so it's never repeated
                        self._record_failure(tool_name, args, result)

                results.append({
                    "tool": tool_name,
                    "arguments": args,
                    "result": result,
                    "verified_success": success
                })
            except Exception as e:
                error_str = str(e)
                tool_name_err = tc.get("function", {}).get("name", "unknown")
                
                # ── Deep Self-Healing (SelfHealer module) ────────
                healer = _get_self_healer()
                if healer:
                    try:
                        heal_result = healer.diagnose_and_heal(
                            original_command=tool_name_err,
                            error_message=error_str,
                            tool_name=tool_name_err,
                        )
                        if heal_result.get("healed"):
                            logger.info("[SelfHealer] Auto-fixed: %s", heal_result.get("fix_applied"))
                            # Retry the tool after healing
                            try:
                                retry_result = self.tool_manager.execute_tool(
                                    tool_name_err, 
                                    tc.get("function", {}).get("arguments", {})
                                )
                                results.append({
                                    "tool": tool_name_err,
                                    "result": retry_result,
                                    "verified_success": True,
                                    "self_healed": True
                                })
                                continue
                            except Exception:
                                pass
                    except Exception as heal_err:
                        logger.debug("[SelfHealer] Healing failed: %s", heal_err)
                
                results.append({
                    "tool": tool_name_err,
                    "result": f"Tool execution error: {error_str}",
                    "verified_success": False
                })
                self._record_failure(
                    tool_name_err,
                    tc.get("function", {}).get("arguments", {}),
                    error_str
                )
        return results

    def _attempt_self_heal(self, tool_name: str, args: dict, error_result) -> Optional[Any]:
        """
        Ask the LLM to fix the tool call arguments and retry once.
        Returns the healed result if successful, None otherwise.
        """
        try:
            heal_prompt = (
                f"The tool '{tool_name}' was called with arguments {json.dumps(args)} "
                f"but it failed with result: {str(error_result)[:500]}. "
                f"Can you fix the arguments and call the tool again? "
                f"Return ONLY a corrected JSON tool call."
            )
            tool_schemas = self.tool_manager.get_tool_schemas()
            plan_result = self.planner.plan_and_select_tools(heal_prompt, "", tool_schemas)

            if plan_result.get("type") == "tools" and plan_result.get("tool_calls"):
                retry_tc = plan_result["tool_calls"][0]
                retry_func = retry_tc.get("function", {})
                retry_name = retry_func.get("name", "")
                retry_args = retry_func.get("arguments", {})
                if isinstance(retry_args, str):
                    retry_args = json.loads(retry_args)

                retry_result = self.tool_manager.execute_tool(retry_name, retry_args)
                if self.verification.verify(retry_name, str(retry_result)):
                    return retry_result
        except Exception as e:
            logger.debug(f"[SelfHeal] Heal attempt failed: {e}")
        return None

    def _record_failure(self, tool_name: str, args, error_result):
        """Store a tool failure in learning memory for future avoidance."""
        try:
            failure_note = (
                f"Tool '{tool_name}' failed with args={json.dumps(args, default=str)[:200]}. "
                f"Error: {str(error_result)[:300]}"
            )
            self.memory.add_learning(failure_note)
            logger.info(f"[SelfHeal] Recorded failure to learning memory: {tool_name}")
        except Exception:
            pass

    def _extract_knowledge(self, user_text: str, response_text: str):
        """
        Background knowledge extraction — runs in a daemon thread.
        Extracts entities and relationships from the conversation and
        stores them in the knowledge graph so Jarvis learns over time.
        """
        try:
            from core.knowledge_extractor import extract_and_store
            extracted = extract_and_store(user_text, response_text, self.memory)
            if extracted:
                logger.info(
                    "[Orchestrator] Knowledge extraction: %d facts from '%s'",
                    len(extracted), user_text[:50]
                )
        except Exception as e:
            logger.debug("[Orchestrator] Knowledge extraction error (non-critical): %s", e)

    def _build_context(self, text: str, conversation_context: str) -> str:
        """Build enriched context from memory, knowledge graph, and message bus."""
        parts = []

        try:
            # 1. Core Identity & Durable Memory (Top Priority)
            identity = self.memory.get_core_identity()
            if identity:
                parts.append(f"CORE IDENTITY:\n{identity}")
                
            durable_mem = self.memory.get_durable_memory()
            if durable_mem:
                parts.append(f"DURABLE MEMORY:\n{durable_mem}")

            # Recent conversations
            past_context = self.memory.retrieve_relevant_conversation(text, n_results=3)
            if past_context:
                parts.append("Recent Conversations:\n" + "\n".join(past_context))

            # Semantic learnings
            learnings = self.memory.retrieve_relevant_learnings(text, n_results=2)
            if learnings:
                parts.append("Relevant Learnings:\n" + "\n".join(learnings))

            # Knowledge Graph — full summary of everything Jarvis knows
            kg_summary = self.memory.get_all_triplets_summary(max_entries=50)
            if kg_summary:
                parts.append(f"Known Facts About User:\n{kg_summary}")
        except Exception as e:
            logger.warning("[Orchestrator] Memory retrieval warning: %s", e)

        # Conversation context from ConversationManager
        if conversation_context:
            parts.insert(0, conversation_context)

        # Message bus context (recent agent activity)
        bus_context = self.bus.get_context_summary()
        if bus_context:
            parts.append(f"Recent activity:\n{bus_context}")

        # Active Screen & Window state
        try:
            from core.screen_monitor import get_screen_monitor
            screen_summary = get_screen_monitor().get_context_summary()
            if screen_summary:
                parts.append(f"Current Desktop State:\n{screen_summary}")
        except Exception:
            pass

        return "\n\n".join(parts)

    # Signals that a request is an open-ended, multi-step goal best handled by
    # the adaptive ReAct loop rather than a single-shot tool selection.
    # Short replies that confirm or cancel a held-back dangerous action.
    _AFFIRMATIONS = frozenset({
        "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed",
        "do it", "go ahead", "proceed", "affirmative", "yes please", "please do",
        "continue", "approved", "approve",
    })
    _DENIALS = frozenset({
        "no", "nope", "nah", "cancel", "stop", "don't", "dont", "abort",
        "never mind", "nevermind", "forget it", "no thanks", "negative",
    })

    def _should_confirm(self, tool_name: str) -> bool:
        """Whether this tool must be confirmed before running on the single-shot path."""
        if self.autonomy == "full":
            return False
        meta = self.tool_manager.tools.get(tool_name, {})
        return is_dangerous_tool(tool_name, meta)

    def _resolve_pending_confirmation(self, text: str) -> Optional[dict]:
        """Handle a bare 'yes'/'no' answering a held-back dangerous action.

        Returns a response dict when ``text`` resolved a pending action, or
        None when there was nothing pending (or the reply wasn't a yes/no, in
        which case the pending action is dropped rather than left to fire
        later against an unrelated command).
        """
        pending = self._pending_action
        if not pending:
            return None

        reply = re.sub(r"[\.!\?]+$", "", text.lower().strip())
        tool_name, args = pending["tool"], pending["args"]

        if reply in self._AFFIRMATIONS:
            self._pending_action = None
            logger.info("[Orchestrator] User confirmed '%s' — executing.", tool_name)
            result = self.tool_manager.execute_tool(tool_name, args)
            success = self.verification.verify(tool_name, str(result))
            self.bus.publish("tool_executed", "orchestrator",
                             {"tool": tool_name, "success": success})
            return {
                "success": success,
                "response": str(result) if success else f"That didn't work, sir: {result}",
                "response_stream": None,
                "action": f"Confirmed: {tool_name}",
            }

        if reply in self._DENIALS:
            self._pending_action = None
            logger.info("[Orchestrator] User cancelled '%s'.", tool_name)
            return {
                "success": True,
                "response": "Cancelled, sir. I haven't touched anything.",
                "response_stream": None,
                "action": f"Cancelled: {tool_name}",
            }

        # Anything else means they've moved on — drop the stale pending action
        # so a later stray "yes" can't trigger it.
        logger.info("[Orchestrator] Dropping stale pending action '%s'.", tool_name)
        self._pending_action = None
        return None

    _AGENTIC_SIGNALS = (
        " and then ", " then ", " after that ", " once you ", " after you ",
        " for each ", " for every ", " keep ", " until ", " one by one ",
        "step by step", "figure out", "research ", "look into", "find out",
        "go through", "organize", "clean up", "set up", "look for",
        "and send", "and email", "and save", "and download", "and open",
        "whatever it takes", "do everything", "sort out", "take care of",
    )

    # Imperative verbs that denote a discrete action. Two or more in one command
    # (joined by "and"/"then"/comma) means it's multi-step and belongs in the
    # agentic loop — e.g. "open Spotify and play a song" (open + play).
    _ACTION_VERBS = frozenset({
        "open", "close", "launch", "start", "play", "pause", "stop", "search",
        "find", "google", "write", "type", "create", "make", "build", "send",
        "email", "message", "text", "call", "set", "turn", "increase", "decrease",
        "mute", "unmute", "download", "upload", "save", "delete", "remove", "read",
        "tell", "show", "check", "summarize", "translate", "record", "screenshot",
        "schedule", "remind", "add", "move", "copy", "rename", "install",
        "uninstall", "update", "run", "execute", "browse", "navigate", "click",
        "compose", "reply", "post", "share", "book", "order", "buy", "generate",
    })

    def _is_agentic_goal(self, text: str) -> bool:
        """Heuristic: should this command run through the multi-step agentic loop?

        Kept conservative so simple, latency-sensitive commands stay on the fast
        single-shot path. Triggers on explicit sequencing/conditional phrasing,
        or when a command chains two or more distinct actions together.
        """
        if not self.agentic_enabled:
            return False

        t = f" {text.lower().strip()} "

        # Explicit multi-step / open-ended phrasing.
        if any(sig in t for sig in self._AGENTIC_SIGNALS):
            return True

        # Two or more distinct action verbs joined by a connector = multi-step.
        # Catches short chains the old word-count rule missed, e.g.
        # "open Spotify and play a song" and "open Notepad and write a haiku".
        has_connector = (" and " in t) or (" then " in t) or ("," in text)
        if has_connector:
            verbs = {w for w in re.findall(r"[a-z]+", t) if w in self._ACTION_VERBS}
            if len(verbs) >= 2:
                return True

        return False

    def _execute_agentic(self, text: str, context: str) -> dict:
        """Run an open-ended goal through the ReAct agentic loop.

        The loop reasons, calls a tool, observes the real result, and re-plans —
        repeating until the goal is met. Returns the standard response dict.
        """
        logger.info("[Orchestrator] Routing to agentic ReAct loop: '%s'", text[:80])
        self.bus.publish("agentic_start", "orchestrator", {"goal": text})
        try:
            loop = self._get_agentic_loop()
            result = loop.run(text, context=context)
            return {
                "success": result.success,
                "response": result.response,
                "response_stream": None,
                "action": f"Agentic workflow ({len(result.steps)} steps)",
            }
        except Exception as e:
            logger.error("[Orchestrator] Agentic loop failed, falling back to single-shot: %s", e)
            # Graceful degradation: never leave the user without a response.
            return self._execute_single(text, context)

    def _decompose_if_needed(self, text: str) -> List[str]:
        """
        Check if the request contains multiple independent tasks.
        Uses simple heuristics for task decomposition.
        """
        self._last_decomposition_mode = "parallel"

        # Sequential separators — subtask 2 depends on subtask 1
        sequential_separators = [" and then ", " then ", " after that "]
        for sep in sequential_separators:
            if sep in text.lower():
                parts = re.split(re.escape(sep), text, flags=re.IGNORECASE)
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) > 1:
                    self._last_decomposition_mode = "sequential"
                    logger.info("[Orchestrator] Decomposed into %d SEQUENTIAL subtasks: %s", len(parts), parts)
                    return parts

        # Parallel separators — truly independent tasks
        parallel_separators = [" also ", " and also "]
        for sep in parallel_separators:
            if sep in text.lower():
                parts = re.split(re.escape(sep), text, flags=re.IGNORECASE)
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) > 1:
                    self._last_decomposition_mode = "parallel"
                    logger.info("[Orchestrator] Decomposed into %d PARALLEL subtasks: %s", len(parts), parts)
                    return parts

        return [text]

    def _execute_sequential(self, subtasks: List[str], context: str) -> dict:
        """Execute subtasks one after another (for dependent tasks)."""
        import time
        all_responses = []
        all_success = True

        for i, subtask in enumerate(subtasks):
            logger.info("[Orchestrator] Sequential step %d/%d: '%s'", i + 1, len(subtasks), subtask)
            result = self._execute_single(subtask, context)
            all_responses.append(result.get("response", "Done"))
            if not result.get("success", True):
                all_success = False

            # Wait between steps for UI to settle
            if i < len(subtasks) - 1:
                time.sleep(2.0)

        return {
            "success": all_success,
            "response": " ".join(r for r in all_responses if r),
            "response_stream": None,
            "action": f"Executed {len(subtasks)} subtasks sequentially"
        }

    def _execute_parallel(self, subtasks: List[str], context: str) -> dict:
        """Execute multiple subtasks in parallel."""
        futures = {}
        for subtask in subtasks:
            future = self.executor.submit(self._execute_single, subtask, context)
            futures[future] = subtask

        all_responses = []
        all_success = True

        for future in as_completed(futures):
            try:
                result = future.result(timeout=120)
                all_responses.append(result.get("response", "Done"))
                if not result.get("success", True):
                    all_success = False
            except Exception as e:
                all_responses.append(f"Failed: {futures[future]} ({e})")
                all_success = False

        return {
            "success": all_success,
            "response": " ".join(all_responses),
            "response_stream": None,
            "action": f"Executed {len(subtasks)} subtasks in parallel"
        }

    def _check_fast_path(self, text: str) -> Optional[dict]:
        """Fast path regex router for instant command execution."""
        text_lower = text.lower().strip()
        text_clean = re.sub(r'^(?:please\s+|jarvis\s+|hey\s+jarvis\s+|can\s+you\s+|could\s+you\s+|just\s+)+', '', text_lower)
        text_clean = re.sub(r'[\.!\?]+$', '', text_clean).strip()
        text_clean = re.sub(r'\s+please$', '', text_clean).strip()

        KNOWN_WEBSITES = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "gmail": "https://mail.google.com",
            "github": "https://github.com",
            "reddit": "https://reddit.com",
            "twitter": "https://twitter.com",
            "x": "https://x.com",
            "instagram": "https://instagram.com",
            "facebook": "https://facebook.com",
            "linkedin": "https://linkedin.com",
            "netflix": "https://netflix.com",
            "spotify": "https://open.spotify.com",
            "chatgpt": "https://chatgpt.com",
            "whatsapp": "https://web.whatsapp.com",
            "amazon": "https://www.amazon.com",
            "wikipedia": "https://www.wikipedia.org",
            "twitch": "https://www.twitch.tv",
            "discord": "https://discord.com/app",
            "telegram": "https://web.telegram.org",
        }

        # 1. Open Website / Web Services
        match = re.match(r'^(?:open|go\s+to|visit|launch\s+website)\s+(?:website\s+)?([a-zA-Z0-9_\-\.]+)(?:\s+website)?$', text_clean)
        if match:
            target = match.group(1).lower().strip()
            if target in KNOWN_WEBSITES:
                url = KNOWN_WEBSITES[target]
                self.tool_manager.execute_tool("open_website", {"url": url})
                return {"success": True, "response": f"Opening {target.capitalize()} for you, sir.", "action": f"FastPath: Open {target}"}
            elif target.startswith(("http://", "https://", "www.")) or re.search(r'\.(com|org|net|io|app|ai|co|gov|edu|tv)$', target):
                url = target if target.startswith(("http://", "https://")) else f"https://{target}"
                self.tool_manager.execute_tool("open_website", {"url": url})
                return {"success": True, "response": f"Opening {target} for you, sir.", "action": f"FastPath: Open {target}"}

        # 2. Google Search
        match = re.match(r'^(?:search\s+google\s+for|search\s+for\s+(.+?)\s+on\s+google|search\s+(.+?)\s+on\s+google|google\s+search\s+for|google\s+search|google)\s+(.+)$', text_clean)
        if match:
            groups = [g for g in match.groups() if g]
            query = groups[-1].strip() if groups else ""
            if query:
                res = self.tool_manager.execute_tool("search_google", {"query": query})
                return {"success": True, "response": str(res), "action": f"FastPath: Google {query}"}

        # 3. YouTube Search / Play
        match = re.match(r'^(?:play|search\s+youtube\s+for|search\s+for\s+(.+?)\s+on\s+youtube|search\s+(.+?)\s+on\s+youtube)\s+(.+)$', text_clean)
        if match and "spotify" not in text_clean:
            groups = [g for g in match.groups() if g]
            query = groups[-1].strip() if groups else ""
            if query:
                res = self.tool_manager.execute_tool("play_youtube", {"query": query})
                return {"success": True, "response": str(res), "action": f"FastPath: YouTube {query}"}

        # 4. Play Spotify
        match = re.match(r'^play\s+(.+?)\s+on\s+spotify$', text_clean)
        if match:
            query = match.group(1).strip()
            res = self.tool_manager.execute_tool("play_spotify", {"query": query})
            return {"success": True, "response": str(res), "action": f"FastPath: Spotify {query}"}

        # 5. Open Application
        match = re.match(r'^(?:open|launch|start)\s+([a-zA-Z0-9_\-\s]+)$', text_clean)
        if match and not any(kw in text_clean for kw in [" and ", " to ", " send ", " text ", " message ", " file "]):
            app = match.group(1).strip()
            if app in KNOWN_WEBSITES:
                url = KNOWN_WEBSITES[app]
                self.tool_manager.execute_tool("open_website", {"url": url})
                return {"success": True, "response": f"Opening {app.capitalize()} for you, sir.", "action": f"FastPath: Open {app}"}
            res = self.tool_manager.execute_tool("open_application", {"app_name": app})
            res_str = str(res)
            success = not (res_str.startswith("Could not") or "failed" in res_str.lower() or "error" in res_str.lower())
            return {"success": success, "response": res_str, "action": f"FastPath: Launch {app}"}

        # 6. Close / Kill Application
        match = re.match(r'^(?:close|kill|end|terminate|quit)\s+([a-zA-Z0-9_\-\s]+)$', text_clean)
        if match and match.group(1).strip() not in ["all windows", "everything"]:
            app = match.group(1).strip()
            res = self.tool_manager.execute_tool("close_application", {"app_name": app})
            return {"success": True, "response": str(res), "action": f"FastPath: Close {app}"}

        # 7. Time & Date Queries
        if text_clean in ["what is the time", "what time is it", "time", "what's the time", "current time", "tell me the time"]:
            import datetime
            now = datetime.datetime.now().strftime("%I:%M %p")
            return {"success": True, "response": f"It's {now}, sir.", "action": "FastPath: Time"}

        if text_clean in ["what is the date", "what is today's date", "what's the date", "today's date", "date"]:
            import datetime
            today = datetime.datetime.now().strftime("%A, %B %d, %Y")
            return {"success": True, "response": f"Today is {today}, sir.", "action": "FastPath: Date"}

        # 8. Volume Controls
        match = re.match(r'^(?:set\s+volume\s+to|volume\s+to|set\s+volume|volume)\s+(\d+)$', text_clean)
        if match:
            level = int(match.group(1))
            res = self.tool_manager.execute_tool("set_volume", {"level": level})
            return {"success": True, "response": str(res), "action": f"FastPath: Volume {level}"}

        if text_clean in ["mute", "unmute", "mute volume", "silence audio", "unmute volume"]:
            res = self.tool_manager.execute_tool("mute_volume", {})
            return {"success": True, "response": str(res), "action": "FastPath: Mute"}

        # 9. Brightness Controls
        match = re.match(r'^(?:set\s+brightness\s+to|brightness\s+to|set\s+brightness|brightness)\s+(\d+)$', text_clean)
        if match:
            level = int(match.group(1))
            res = self.tool_manager.execute_tool("set_brightness", {"level": level})
            return {"success": True, "response": str(res), "action": f"FastPath: Brightness {level}"}

        # 10. Screenshot
        if text_clean in ["take a screenshot", "screenshot", "take screenshot", "capture screen"]:
            res = self.tool_manager.execute_tool("take_screenshot", {})
            return {"success": True, "response": str(res), "action": "FastPath: Screenshot"}

        # 11. System Status
        if text_clean in ["system status", "system info", "how is the system", "pc status", "battery", "battery status", "cpu usage", "ram usage"]:
            res = self.tool_manager.execute_tool("get_system_status", {})
            return {"success": True, "response": str(res), "action": "FastPath: System Status"}

        return None
