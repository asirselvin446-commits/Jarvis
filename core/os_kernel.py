"""
J.A.R.V.I.S. OS Kernel
The main orchestration layer for the AI Operating System.
Now delegates to the multi-agent Orchestrator for intelligent task routing.

Pipeline: Speech -> Orchestrator -> Agent Selection -> Tool Execution ->
          Verification -> Response -> Memory Update
"""

from core.orchestrator import Orchestrator


class OSKernel:
    """
    Thin wrapper around the Orchestrator.
    Maintains backward compatibility with the web server and MCP server
    which call kernel.process_command(text).
    """

    def __init__(self):
        self.orchestrator = Orchestrator()

    def process_command(self, text: str) -> dict:
        """Process a spoken command through the multi-agent pipeline."""
        return self.orchestrator.process_command(text)

