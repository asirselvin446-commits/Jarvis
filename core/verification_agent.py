"""
J.A.R.V.I.S. Verification Agent
Checks if a tool execution succeeded.
"""

class VerificationAgent:
    def __init__(self):
        pass

    def verify(self, tool_name: str, result: str) -> bool:
        """
        Simple verification based on string heuristics for now.
        Can be upgraded to use Qwen 2.5 7B for semantic verification.
        """
        result_lower = str(result).lower()
        
        if "failed" in result_lower:
            return False
        if "could not" in result_lower or "couldn't" in result_lower:
            return False
        if "error" in result_lower:
            return False
            
        return True
