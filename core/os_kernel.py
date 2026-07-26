"""
J.A.R.V.I.S. OS Kernel
The main orchestration layer for the AI Operating System.
Replaces CommandRouter.
Pipeline: Speech -> Memory -> Planner (Qwen2.5) -> Tool Selection -> Execution -> Verification -> Response -> Memory Update
"""

from core.planner import Planner
from core.memory import MemoryManager
from core.tool_manager import ToolManager
from core.verification_agent import VerificationAgent

class OSKernel:
    def __init__(self):
        self.memory = MemoryManager()
        self.tool_manager = ToolManager()
        self.planner = Planner()
        self.verification = VerificationAgent()
        self.tool_schemas = self.tool_manager.get_tool_schemas()

    def process_command(self, text: str) -> dict:
        """Process a spoken command through the OS pipeline."""
        import json
        import traceback
        
        response_dict = {
            "success": True,
            "response": "",
            "action": ""
        }

        try:
            # 1. Retrieve Context from Memory
            try:
                past_context = self.memory.retrieve_relevant_conversation(text, n_results=3)
                context_str = "\n".join(past_context)
            except Exception:
                context_str = ""  # Memory failure is non-fatal

            # 2. Planning and Tool Selection (via Qwen 2.5 7B)
            plan_result = self.planner.plan_and_select_tools(text, context_str, self.tool_schemas)

            # 3. Execution Phase
            if plan_result["type"] == "tools":
                tool_results = []
                for tc in plan_result["tool_calls"]:
                    try:
                        tool_name = tc["function"]["name"]
                        args = tc["function"]["arguments"]
                        if isinstance(args, str):
                            args = json.loads(args)

                        # Execute Tool
                        result = self.tool_manager.execute_tool(tool_name, args)
                        
                        # Verify Execution
                        success = self.verification.verify(tool_name, result)
                        
                        tool_results.append({
                            "tool": tool_name,
                            "arguments": args,
                            "result": result,
                            "verified_success": success
                        })
                    except Exception as e:
                        tool_results.append({
                            "tool": tc.get("function", {}).get("name", "unknown"),
                            "result": f"Tool execution error: {str(e)}",
                            "verified_success": False
                        })
                
                # 4. Generate conversational response based on tool results
                try:
                    final_response = self.planner.evaluate_result(text, tool_results)
                except Exception:
                    # If the LLM summary fails, build a simple response from tool results
                    final_response = ". ".join(
                        str(tr.get("result", "Done")) for tr in tool_results
                    )
                
                response_dict["response"] = final_response
                response_dict["action"] = f"Executed {len(tool_results)} tools"
                
            elif plan_result["type"] == "response":
                response_dict["response"] = plan_result["content"]
                response_dict["action"] = "Answered question"
            else:
                response_dict["success"] = False
                response_dict["response"] = plan_result.get("content", "I encountered an error while processing that.")
                response_dict["action"] = "Error"

            # 5. Memory Update (non-fatal if it fails)
            try:
                self.memory.add_conversation("user", text)
                self.memory.add_conversation("jarvis", response_dict["response"])
            except Exception:
                pass  # Memory save failure is non-fatal

        except Exception as e:
            error_trace = traceback.format_exc()
            print(f"[OSKernel] Pipeline error: {error_trace}")
            response_dict["success"] = False
            response_dict["response"] = f"Pipeline error: {str(e)}"
            response_dict["action"] = "Error"

        return response_dict
