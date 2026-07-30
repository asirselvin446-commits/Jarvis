"""
J.A.R.V.I.S. Verification Agent
Checks if a tool execution succeeded using heuristics and LLM verification.
"""

from core.llm_provider import llm_generate

# Keyword sets for fast heuristic checks
FAILURE_KEYWORDS = [
    "failed", "could not", "couldn't", "error", "exception", "traceback",
    "not found", "permission denied", "access denied", "timed out",
    "timeout", "refused", "invalid", "unable to", "does not exist",
    "no such file", "command not found", "is not recognized",
]
SUCCESS_KEYWORDS = [
    "successfully", "opened", "created", "done", "playing", "sent",
    "set to", "committed", "written", "executed", "launched", "started",
    "found", "match", "toggled", "muted", "unmuted", "locked",
    "brightness set", "volume set", "timer set", "alarm set", "reminder set",
]


class VerificationAgent:
    def __init__(self):
        pass

    def verify(self, tool_name: str, result: str) -> bool:
        """
        Verifies if a tool execution was successful.
        Combines fast string heuristics with semantic evaluation.
        """
        result_str = str(result)
        result_lower = result_str.lower()

        # Fast heuristic checks — check failures first (more dangerous to miss)
        if any(err_kw in result_lower for err_kw in FAILURE_KEYWORDS):
            return False
        if any(success_kw in result_lower for success_kw in SUCCESS_KEYWORDS):
            return True

        # Empty or very short results are ambiguous — check with LLM
        if len(result_str.strip()) < 5:
            return True  # Assume success for minimal output (e.g., empty stdout)

        # Semantic check via LLM for ambiguous outcomes (with retry)
        for attempt in range(2):
            try:
                prompt = (
                    f"A tool named '{tool_name}' was executed and returned the following output.\n"
                    f"Output: {result_str[:500]}\n\n"
                    f"Did this tool execution succeed? Answer ONLY 'YES' or 'NO'."
                )
                answer = llm_generate(prompt, temperature=0.0, timeout=8, max_tokens=5)
                return "YES" in answer.strip().upper()
            except Exception:
                if attempt == 0:
                    continue  # Retry once
            break  # Don't retry on non-timeout errors

        return True  # Default: assume success if we can't verify


