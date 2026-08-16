"""
J.A.R.V.I.S. OS Kernel
═══════════════════════
The main orchestration layer for the AI Operating System.
Uses the unified Orchestrator pipeline (Planner → Tools → Response).
"""

import os
import re
import json
import time
import logging
import traceback
from typing import Optional

from core.orchestrator import Orchestrator
from core.tool_manager import ToolManager
from core.memory import MemoryManager

logger = logging.getLogger("jarvis.kernel")


class OSKernel:
    """
    Thin wrapper around the unified Orchestrator.
    Adds fast-path regex routing for zero-latency common commands,
    workflow execution, and SkillManager integration.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        # Singleton: there is exactly one kernel. Plugins and UI modules all call
        # OSKernel() expecting the same instance, and plugin discovery can import
        # modules that reference the kernel mid-construction — a second instance
        # would spawn duplicate Gateways, Cron loops, and Dreamers.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Only run the heavy, side-effecting initialization once. Re-entrant
        # OSKernel() calls (e.g. from a plugin imported during Orchestrator
        # construction) return here immediately instead of restarting everything.
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.orchestrator = Orchestrator()
        self.tool_manager = self.orchestrator.tool_manager
        self.memory = self.orchestrator.memory

        # Subscribe to hot-reloads from the Self-Evolution engine and Workspaces
        from core.message_bus import get_message_bus
        get_message_bus().subscribe("system.reload_plugins", self._handle_plugin_reload)
        get_message_bus().subscribe("system.switch_workspace", self._handle_switch_workspace)

        # Initialize VisionAgent for screen monitoring (if available)
        try:
            from core.vision import VisionAgent, set_vision_instance
            vision_agent = VisionAgent(self.tool_manager, self.memory)
            set_vision_instance(vision_agent)
        except Exception as e:
            logger.warning("[OSKernel] VisionAgent initialization skipped: %s", e)

        # Initialize the Omni-Channel Gateway (webhooks) on its own port so it
        # does not collide with the web UI server on WEB_SERVER_PORT.
        try:
            import config
            from core.gateway import Gateway
            self.gateway = Gateway(self, port=getattr(config, "GATEWAY_PORT", 5100))
            self.gateway.start()
        except Exception as e:
            logger.error("[OSKernel] Failed to start Gateway: %s", e)

        # Initialize the Dreaming Daemon
        try:
            from core.dreamer import DreamingDaemon
            self.dreamer = DreamingDaemon(self.memory, get_message_bus(), interval_seconds=3600)
            self.dreamer.start()
        except Exception as e:
            logger.error("[OSKernel] Failed to start Dreaming Daemon: %s", e)

        # Initialize the Cron Engine for Advanced Automations
        try:
            from core.cron_engine import CronEngine
            self.cron = CronEngine()
            self.cron.start()
            # Register core recurring jobs now that the loop is live. Plugins no
            # longer register these at import time (that caused a re-entrant
            # kernel-construction cascade).
            self._register_core_cron_jobs()
        except Exception as e:
            logger.error("[OSKernel] Failed to start Cron Engine: %s", e)

        # Agent Swarm: track background sub-agents
        self._sub_agents = {}  # {task_id: {"thread": Thread, "status": str, "result": str}}
        self._sub_agent_counter = 0

        self._load_state()
        print(f"[OSKernel] Initialized with unified Orchestrator ({len(self.tool_manager.tools)} tools)")

    def _register_core_cron_jobs(self):
        """Register built-in recurring jobs (e.g. the morning briefing).

        Called once, after the cron loop is running. Jobs are keyed by id, so
        this is idempotent even if invoked again.
        """
        try:
            from plugins.morning_briefing import _cron_check
            self.cron.add_job("morning_briefing", 60, _cron_check)
        except Exception as e:
            logger.debug("[OSKernel] Core cron job registration skipped: %s", e)

    def spawn_sub_agent(self, task_description: str) -> str:
        """
        Spawns a background sub-agent (daemon thread) that processes
        a task through the Orchestrator independently.
        Returns a task_id for tracking.
        """
        import threading

        self._sub_agent_counter += 1
        task_id = f"sub_agent_{self._sub_agent_counter}"

        def _run():
            self._sub_agents[task_id]["status"] = "running"
            try:
                result = self.orchestrator.process_command(task_description)
                self._sub_agents[task_id]["status"] = "completed"
                self._sub_agents[task_id]["result"] = result.get("response", "Done.")

                # Announce completion via message bus
                from core.message_bus import get_message_bus
                get_message_bus().publish("sub_agent.completed", task_id, {
                    "task": task_description,
                    "result": result.get("response", "")[:500],
                })
                logger.info(f"[OSKernel] Sub-agent '{task_id}' completed: {task_description[:80]}")
            except Exception as e:
                self._sub_agents[task_id]["status"] = "failed"
                self._sub_agents[task_id]["result"] = str(e)
                logger.error(f"[OSKernel] Sub-agent '{task_id}' failed: {e}")

        thread = threading.Thread(target=_run, daemon=True, name=task_id)
        self._sub_agents[task_id] = {"thread": thread, "status": "pending", "result": None, "task": task_description}
        thread.start()
        logger.info(f"[OSKernel] Spawned sub-agent '{task_id}': {task_description[:80]}")
        return task_id

    def get_sub_agent_status(self) -> list:
        """Returns a list of all sub-agent statuses."""
        return [
            {"id": tid, "task": info["task"][:100], "status": info["status"], "result": (info["result"] or "")[:200]}
            for tid, info in self._sub_agents.items()
        ]

    def _handle_plugin_reload(self, msg):
        """Called when a new plugin is dynamically generated."""
        logger.info(f"[OSKernel] Hot-reloading plugins triggered by event: {msg.payload}")
        self.tool_manager.reload_plugins()

    def _handle_switch_workspace(self, msg):
        """Called when a user requests to switch to a different workspace."""
        new_ws = msg.payload.get("workspace_name", "default")
        logger.info(f"[OSKernel] Switching active workspace to: {new_ws}")
        self.tool_manager.set_workspace(new_ws)

    def _load_state(self):
        """Recover state from disk if it crashed previously."""
        if os.path.exists("kernel_state.json"):
            try:
                import json
                with open("kernel_state.json", "r") as f:
                    state = json.load(f)
                    
                    # Restore active workspace
                    ws = state.get("active_workspace", "default")
                    self.tool_manager.set_workspace(ws)
                    
                    logger.info("[OSKernel] Recovered previous state from %s", state.get('timestamp'))
            except Exception as e:
                logger.warning("[OSKernel] Failed to load state: %s", e)

    def shutdown(self):
        """Gracefully shut down the kernel and save state."""
        print("[OSKernel] Initiating graceful shutdown...")
        try:
            if hasattr(self, 'cron'):
                self.cron.stop()
            if hasattr(self, 'dreamer'):
                self.dreamer.stop()
                
            import json
            from datetime import datetime
            state = {
                "timestamp": datetime.now().isoformat(),
                "active_workspace": getattr(self.tool_manager, "workspace", "default")
            }
            with open("kernel_state.json", "w") as f:
                json.dump(state, f)
            print("[OSKernel] Kernel state saved successfully.")
        except Exception as e:
            print(f"[OSKernel] Error saving state: {e}")

    def process_command(self, text: str, conversation_context: str = "") -> dict:
        """
        Process a spoken command through the unified pipeline.
        
        Pipeline:
          1. Check workflow triggers (predefined JSON workflows)
          2. Fast-path regex router (instant, no LLM)
          3. SkillManager domain skills (computer use, messaging, etc.)
          4. Unified Orchestrator (LLM + tool calling)
        """
        try:
            # 0. Emergency stop — halt any running autonomous task immediately.
            if text.strip().lower().rstrip(".!") in (
                "stop", "stop it", "stop everything", "cancel", "cancel task",
                "abort", "halt", "emergency stop", "stop the task",
            ):
                from core.control import get_control_plane
                get_control_plane().request_stop("voice/text command")
                return {"success": True, "response": "Stopped. Halting all active tasks, sir.",
                        "action": "EmergencyStop", "response_stream": None}

            # 1. Check for predefined workflows
            try:
                from core.workflow_composer import WorkflowComposer
                composer = WorkflowComposer(self)
                text_lower = text.lower()
                for w_name in composer.get_workflow_names():
                    if w_name in text_lower or f"{w_name} mode" in text_lower:
                        response = composer.execute_workflow(w_name)
                        return {"success": True, "response": response, "action": f"Workflow: {w_name}"}
            except Exception:
                pass

            # 1.5 Open-ended / multi-step goal → go straight to the agentic loop.
            #     Fast-path and single-purpose skills only handle the FIRST clause
            #     (e.g. "open youtube and play Shape of You" would just open
            #     YouTube), so multi-step commands must bypass them and reach the
            #     Orchestrator's adaptive ReAct loop.
            try:
                if self.orchestrator._is_agentic_goal(text):
                    logger.info("[OSKernel] Routing multi-step goal to agentic Orchestrator: '%s'", text[:60])
                    return self.orchestrator.process_command(text, conversation_context)
            except Exception as e:
                logger.debug("[OSKernel] Agentic pre-routing check skipped: %s", e)

            # 2. Fast-path regex router (zero-latency for common commands)
            fast_result = self._check_fast_path(text)
            if fast_result:
                # Store in memory
                try:
                    self.memory.add_conversation("user", text)
                    if not fast_result.get("response_stream"):
                        self.memory.add_conversation("jarvis", fast_result["response"])
                except Exception:
                    pass
                return fast_result

            # 3. Try SkillManager for specialized domain skills
            try:
                from core.skills.skill_manager import get_skill_manager
                sm = get_skill_manager()
                matched_skill = sm.select_skill_for_intent(text)

                # Route to SkillManager if a specialized skill matched
                if matched_skill.name != "universal":
                    logger.info("[OSKernel] Routing to SkillManager skill: '%s'", matched_skill.name)
                    exec_result = sm.execute_intent(text, conversation_context)

                    resp_msg = (
                        exec_result.metadata.get("response")
                        if (exec_result.metadata and "response" in exec_result.metadata)
                        else f"I've completed your request: '{text}'."
                    )

                    result = {
                        "success": exec_result.success,
                        "response": resp_msg if exec_result.success else f"Action incomplete: {exec_result.failure_reason}",
                        "action": f"Skill: {matched_skill.name}",
                        "response_stream": None
                    }

                    # Store in memory
                    try:
                        self.memory.add_conversation("user", text)
                        self.memory.add_conversation("jarvis", result["response"])
                    except Exception:
                        pass

                    return result
            except Exception as e:
                logger.warning("[OSKernel] SkillManager routing failed: %s", e)

            # 4. Unified Orchestrator (LLM + function calling + tool execution)
            return self.orchestrator.process_command(text, conversation_context)

        except Exception as e:
            logger.error("[OSKernel] Pipeline error: %s", traceback.format_exc())
            return {
                "success": False,
                "response": f"Pipeline error: {str(e)}",
                "action": "Error",
                "response_stream": None
            }

    def _check_fast_path(self, text: str) -> Optional[dict]:
        """
        Lightning-fast regex router for common commands.
        Bypasses the LLM entirely for zero-latency execution.
        """
        text_lower = text.lower().strip()
        # Strip common conversational prefixes and suffixes
        text_clean = re.sub(r'^(?:please\s+|jarvis\s+|hey\s+jarvis\s+|can\s+you\s+|could\s+you\s+|just\s+)+', '', text_lower)
        text_clean = re.sub(r'[\.!\?]+$', '', text_clean).strip()
        text_clean = re.sub(r'\s+please$', '', text_clean).strip()

        # 1. Open Website / Web Services
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
        }

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
            # Pick query from matched groups
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

        # 5. Open Application (e.g. "open notepad", "launch vs code", "open calculator")
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

        # 11. System Status / Battery / CPU / RAM
        if text_clean in ["system status", "system info", "how is the system", "pc status", "battery", "battery status", "cpu usage", "ram usage"]:
            res = self.tool_manager.execute_tool("get_system_status", {})
            return {"success": True, "response": str(res), "action": "FastPath: System Status"}

        # 12. AI Builders Workflow
        match = re.match(r'^(?:build|create|make)\s+(.+?)\s+(?:using|with|on)\s+(claude|lovable|ai studio|v0|bolt|n8n|chatgpt)$', text_clean)
        if not match:
            match = re.match(r'^ask\s+(claude|lovable|ai studio|v0|bolt|n8n|chatgpt)\s+to\s+(?:build|create|make|write)\s+(.+)$', text_clean)
            if match:
                match = type('obj', (object,), {'group': lambda self, i: match.group(2) if i == 1 else match.group(1)})()

        if match:
            topic = match.group(1).strip()
            builder = match.group(2).strip()
            from plugins.ai_builders import generate_expert_prompt, invoke_ai_builder
            expert_prompt = generate_expert_prompt(topic)
            res = invoke_ai_builder(builder, expert_prompt)
            return {"success": True, "response": f"I have asked {builder.title()} to build that for you, sir.", "action": f"FastPath: Build on {builder.title()}"}

        # 13. Screen Vision (VQA)
        match = re.match(r'^(?:look at my screen and tell me|what am i looking at|describe the screen|read this to me|what is on my screen)(?:\s+(.+))?$', text_clean)
        if match:
            question = match.group(1) if match.group(1) else "What is on the screen?"
            from plugins.display_control import analyze_screen
            res = analyze_screen(question)
            return {"success": True, "response": res, "action": "FastPath: Screen Vision (VQA)"}

        return None
