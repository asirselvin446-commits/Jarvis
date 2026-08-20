"""
J.A.R.V.I.S. FastMCP Server Bridge
══════════════════════════════════
Exposes Jarvis's full dynamic tool registry (105+ tools) over Model Context Protocol (MCP)
via SSE transport (port 8000) and stdio transport.
Compatible with LiveKit Voice Agents, Cursor, Claude Desktop, and FastMCP clients.
"""

import sys
import logging
from core.tool_manager import ToolManager

logger = logging.getLogger("jarvis.mcp_server")


def create_mcp_server(name: str = "JARVIS-MCP", port: int = 8000):
    """
    Constructs a FastMCP server instance populated with all registered Jarvis plugins.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        try:
            from fastmcp import FastMCP
        except ImportError:
            logger.error("Neither 'mcp.server.fastmcp' nor 'fastmcp' is available.")
            return None

    tm = ToolManager()
    server = FastMCP(
        name=name,
        instructions=(
            "You are J.A.R.V.I.S., an advanced AI assistant created by Tony Stark, "
            "controlling a Windows PC environment with complete tool orchestration."
        )
    )

    # 1. Expose Jarvis memory graph as an MCP Resource
    @server.resource("jarvis://memory/graph")
    def get_memory_graph() -> str:
        """Get the full knowledge graph about the user."""
        try:
            from core.memory import get_memory_manager
            # Shared singleton — must NOT close it here, other consumers use it.
            mm = get_memory_manager()
            summary = mm.get_all_triplets_summary()
            return summary or "Knowledge graph is currently empty."
        except Exception as e:
            return f"Error reading memory: {e}"

    # 2. Expose System Status as an MCP Resource
    @server.resource("jarvis://system/status")
    def get_system_status() -> str:
        """Get the current PC environment status (battery, CPU, RAM)."""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
            batt = psutil.sensors_battery()
            b_status = f"{batt.percent}%" if batt else "Unknown"
            return f"CPU: {cpu}%\nRAM: {ram}%\nBattery: {b_status}"
        except Exception as e:
            return f"Status error: {e}"

    # 3. Add a default Prompt for new chat sessions
    @server.prompt("jarvis_assist")
    def jarvis_assist(task: str) -> str:
        """A prompt to ask Jarvis to assist with a specific Windows/Web task."""
        return f"Please use your tools to accomplish the following task: {task}"

    # 4. Register each tool dynamically
    for tool_name, tool_data in tm.tools.items():
        func = tool_data.get("func")
        desc = tool_data.get("description", "")
        if func and callable(func):
            try:
                server.tool(name=tool_name, description=desc)(func)
            except Exception as e:
                logger.debug("Tool '%s' skipped in MCP registration: %s", tool_name, e)

    return server


def run_mcp_server(transport: str = "sse", port: int = 8000):
    """
    Launch the MCP server.
    :param transport: 'sse' (HTTP on port) or 'stdio'
    """
    try:
        server = create_mcp_server(port=port)
        if not server:
            logger.warning("[MCPServer] FastMCP is not installed in the environment.")
            return

        logger.info("[MCPServer] Launching J.A.R.V.I.S. MCP Server on %s (port %d)...", transport, port)
        if transport == "sse":
            server.run(transport="sse")
        else:
            server.run(transport="stdio")
    except Exception as e:
        logger.warning("[MCPServer] Failed to start MCP server on port %d: %s", port, e)


def start_mcp_server(port: int = 8000, transport: str = "sse"):
    """Alias for run_mcp_server for backward and forward compatibility."""
    run_mcp_server(transport=transport, port=port)


if __name__ == "__main__":
    transport_mode = sys.argv[1] if len(sys.argv) > 1 else "sse"
    run_mcp_server(transport=transport_mode)
