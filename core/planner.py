"""
J.A.R.V.I.S. Planner
Breaks down user requests and selects tools using the best available LLM.
Routes automatically to cloud (Gemini Flash) or local (Ollama qwen2.5:7b).
"""

import json
import re
from typing import List, Dict, Any

from core.llm_provider import llm_chat


class Planner:
    def __init__(self):
        pass

    def plan_and_select_tools(self, user_request: str, memory_context: str, tool_schemas: List[dict]) -> dict:
        """
        Uses the LLM provider with tools to determine the action.
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
            "   - To open a website (e.g. 'open youtube', 'open reddit.com', 'go to facebook') → USE `open_website(url=\"...\")`!\n"
            "   - To open a desktop app (e.g. 'open notepad', 'open spotify', 'open chrome') → USE `open_application(app_name=\"...\")`! Do NOT use this for websites like YouTube.\n"
            "   - To set a timer (e.g. 'set a 5 minute timer') → USE `set_timer(duration_seconds=300, label=\"...\")`!\n"
            "   - To set an alarm (e.g. 'set alarm for 7am', 'wake me up at 9:30') → USE `set_alarm(time_str=\"...\", label=\"...\")`!\n"
            "   - To set a reminder (e.g. 'remind me in 10 minutes') → USE `set_reminder(delay_minutes=10, reminder_text=\"...\")`!\n"
            "   - To read a code file → USE `read_code_file(file_path=\"...\")`!\n"
            "   - To write a code file → USE `write_code_file(file_path=\"...\", content=\"...\")`!\n"
            "   - To search code/text in files → USE `search_code(pattern=\"...\", directory=\"...\")`!\n"
            "   - To check git status → USE `git_status(project_dir=\"...\")`!\n"
            "   - To commit code → USE `git_commit(message=\"...\")`!\n"
            "   - To see code changes → USE `git_diff()`!\n"
            "   - To list files in a directory → USE `list_directory(directory=\"...\")`!\n"
            "   - To open a file in VS Code → USE `open_in_vscode(file_path=\"...\", line=1)`!\n"
            "   - To review code quality → USE `code_review(file_path=\"...\")`!\n"
            "   - To run a Python script → USE `execute_python_script(code=\"...\")`!\n"
            "   - To check weather → USE `get_weather(city=\"...\")` or `get_weather_brief(city=\"...\")`!\n"
            "   - To read emails → USE `read_emails(count=5)` or `search_emails(query=\"...\")`!\n"
            "   - To send an email → USE `send_email(to=\"...\", subject=\"...\", body=\"...\")`!\n"
            "   - To check calendar → USE `get_calendar_events(days_ahead=7)`!\n"
            "   - To create a calendar event → USE `create_calendar_event(title=\"...\", start_time=\"...\")`!\n"
            "   - To search Notion → USE `notion_search(query=\"...\")`!\n"
            "   - To create a Notion page → USE `notion_create_page(title=\"...\", content=\"...\")`!\n"
            "   - To send a Slack/Discord message → USE `send_chat_message(message=\"...\")`!\n"
            "   - To record a macro → USE `start_recording_macro(macro_name=\"...\")` then `stop_recording_macro()`!\n"
            "   - To replay a macro → USE `replay_macro(macro_name=\"...\")`!\n"
            "   - To list macros → USE `list_macros()`!\n"
            "   - To create an event trigger → USE `create_event_trigger(name=\"...\", event_type=\"...\", action_tool=\"...\", action_args={...})`!\n"
            "   - To list event triggers → USE `list_event_triggers()`!\n"
            "   - ONLY use `computer_use` for complex multi-step GUI interactions that don't have dedicated tools.\n"
            "3. Only answer directly with text for purely conversational questions (e.g., 'what is 2 + 2?').\n"
            "4. When using computer_use, pass a DETAILED goal description that includes every step needed.\n\n"
            f"Memory Context:\n{memory_context}\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request}
        ]

        try:
            message = llm_chat(messages, tools=tool_schemas, temperature=0.0, timeout=60)

            if "tool_calls" in message and message["tool_calls"]:
                return {"type": "tools", "tool_calls": message["tool_calls"]}
            
            # Fallback: Sometimes smaller models return tool calls as raw text
            # e.g., 'computer_use {"goal": "..."}'
            content = message.get("content", "").strip()
            
            # Strip markdown code blocks that the model might add
            content_clean = re.sub(r'```(?:json|python)?\n?', '', content, flags=re.IGNORECASE)
            content_clean = content_clean.replace('```', '').strip()
            
            # Look for a tool name followed by a JSON object anywhere in the text
            tool_match = re.search(r'([a-zA-Z0-9_]+)\s*(\{.*?\})', content_clean, re.DOTALL)
            if tool_match:
                t_name, t_args = tool_match.groups()
                # Verify it's a known tool
                if any(t["function"]["name"] == t_name for t in tool_schemas):
                    try:
                        # Fix possible double-escaped backslashes from markdown
                        t_args = t_args.replace('\\\\', '\\')
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
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request},
            {"role": "system", "content": f"Tool Execution Results:\n{results_str}"}
        ]
        
        try:
            result = llm_chat(messages, temperature=0.3, timeout=60)
            return result.get("content", "Task completed.")
        except Exception:
            return "Task completed."

    def evaluate_result_stream(self, user_request: str, tool_results: List[dict]):
        """
        After tools execute, stream a final response to the user.
        Yields chunks of text.
        """
        from core.llm_provider import llm_chat_stream
        
        system_prompt = (
            "You are J.A.R.V.I.S. "
            "You just executed some tools to help the user. "
            "Summarize the results in a brief, conversational way (1-2 sentences)."
        )
        
        results_str = json.dumps(tool_results, indent=2)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request},
            {"role": "system", "content": f"Tool Execution Results:\n{results_str}"}
        ]
        
        try:
            yield from llm_chat_stream(messages, temperature=0.3, timeout=60)
        except Exception as e:
            yield "Task completed."

