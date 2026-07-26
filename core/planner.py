"""
J.A.R.V.I.S. Planner
Breaks down user requests and selects tools using Qwen 2.5 7B via Ollama.
"""

import json
import requests
from typing import List, Dict, Any

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:7b"


class Planner:
    def __init__(self):
        pass

    def plan_and_select_tools(self, user_request: str, memory_context: str, tool_schemas: List[dict]) -> dict:
        """
        Uses Ollama's /api/chat endpoint with tools to determine the action.
        Returns a dictionary containing either a 'response' string or a list of 'tool_calls'.
        """
        system_prompt = (
            "You are J.A.R.V.I.S., an advanced AI Operating System controlling the user's Windows PC.\n\n"
            "CRITICAL RULES:\n"
            "1. NEVER roleplay or describe taking an action. You MUST call a tool.\n"
            "2. TOOL SELECTION GUIDELINES:\n"
            "   - To play or search ANYTHING on YouTube (e.g. 'open youtube and play X', 'play Shape of You', 'play Z video') → USE `play_youtube(query=\"...\")`!\n"
            "   - To play ANYTHING on Spotify (e.g. 'play X on Spotify', 'open spotify and play Y') → USE `play_spotify(query=\"...\")`!\n"
            "   - To send a WhatsApp message (e.g. 'text Chandru hi on WhatsApp', 'send message to X') → USE `whatsapp_send_message(contact=\"...\", message=\"...\")`!\n"
            "   - To check CPU, RAM, Battery, or Disk status → USE `get_system_status()`!\n"
            "   - To read or copy to clipboard → USE `clipboard_read()` or `clipboard_write(text=\"...\")`!\n"
            "   - To run shell commands → USE `execute_terminal(command=\"...\")` or `run_powershell(script=\"...\")`!\n"
            "   - To search Google (e.g. 'search google for X') → USE `search_google(query=\"...\")`!\n"
            "   - To open a website (e.g. 'open reddit.com') → USE `open_website(url=\"...\")`!\n"
            "   - To open a desktop app (e.g. 'open notepad', 'open spotify', 'open chrome') → USE `open_application(app_name=\"...\")`!\n"
            "   - ONLY use `computer_use` for complex multi-step GUI interactions that don't have dedicated tools.\n"
            "3. Only answer directly with text for purely conversational questions (e.g., 'what is 2 + 2?').\n"
            "4. When using computer_use, pass a DETAILED goal description that includes every step needed.\n\n"
            f"Memory Context:\n{memory_context}\n"
        )

        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_request}
            ],
            "tools": tool_schemas,
            "stream": False,
            "options": {
                "temperature": 0.0
            }
        }

        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            message = data.get("message", {})

            if "tool_calls" in message and message["tool_calls"]:
                return {"type": "tools", "tool_calls": message["tool_calls"]}
            
            # Fallback: Sometimes smaller models return tool calls as raw text
            # e.g., 'computer_use {"goal": "..."}'
            content = message.get("content", "").strip()
            import re
            
            # Look for a tool name followed by a JSON object
            tool_match = re.search(r'^([a-zA-Z0-9_]+)\s*(\{.*?\})$', content, re.DOTALL)
            if tool_match:
                t_name, t_args = tool_match.groups()
                # Verify it's a known tool
                if any(t["function"]["name"] == t_name for t in tool_schemas):
                    try:
                        import json
                        args_dict = json.loads(t_args)
                        return {
                            "type": "tools",
                            "tool_calls": [{
                                "function": {
                                    "name": t_name,
                                    "arguments": args_dict
                                }
                            }]
                        }
                    except json.JSONDecodeError:
                        pass
                        
            return {"type": "response", "content": content}

        except Exception as e:
            return {"type": "error", "content": f"Planner failed: {e}"}

    def evaluate_result(self, user_request: str, tool_results: List[dict]) -> str:
        """
        After tools execute, generate a final response to the user.
        """
        system_prompt = (
            "You are J.A.R.V.I.S. "
            "You just executed some tools to help the user. "
            "Summarize the results in a brief, conversational way (1-2 sentences)."
        )
        
        results_str = json.dumps(tool_results, indent=2)
        
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_request},
                {"role": "system", "content": f"Tool Execution Results:\n{results_str}"}
            ],
            "stream": False,
            "options": {"temperature": 0.3}
        }
        
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "Task completed.")
        except Exception:
            return "Task completed."
