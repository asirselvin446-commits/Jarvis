"""
J.A.R.V.I.S. MCP Server with Auth & WebSocket
Exposes all Jarvis tools to external agents via Model Context Protocol (SSE).
Now with API key authentication for remote access and WebSocket support.
"""

import json
import asyncio
import base64
from typing import Any
from mcp.server import Server
from mcp.types import Tool, TextContent
from core.tool_manager import ToolManager
from core.remote_access import verify_api_key

# Initialize the ToolManager to discover plugins
tool_mgr = ToolManager()

# Create the MCP Server
app = Server("jarvis-mcp")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """Provide a list of available tools to the MCP client."""
    tools = []
    for name, data in tool_mgr.tools.items():
        tools.append(Tool(
            name=data["name"],
            description=data["description"],
            inputSchema=data["parameters"]
        ))
    return tools

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a tool called by the MCP client."""
    try:
        result = tool_mgr.execute_tool(name, arguments)
        
        if isinstance(result, str):
            content_text = result
        else:
            content_text = json.dumps(result, indent=2)
            
        return [TextContent(type="text", text=content_text)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error executing tool '{name}': {str(e)}")]


# ─── Auth Middleware ─────────────────────────────────────────────

from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.websockets import WebSocket, WebSocketDisconnect
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from mcp.server.sse import SseServerTransport
import uvicorn


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that checks for API key in:
      - Authorization: Bearer <key>
      - X-API-Key: <key>
      - ?api_key=<key> query parameter
    
    Local requests (127.0.0.1) bypass auth for development.
    """

    async def dispatch(self, request: Request, call_next):
        # Allow local requests without auth
        client_host = request.client.host if request.client else ""
        if client_host in ("127.0.0.1", "::1", "localhost"):
            return await call_next(request)

        # Health endpoint doesn't need auth
        if request.url.path in ("/health", "/api/status"):
            return await call_next(request)

        # Check for API key
        api_key = None

        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]

        # Check X-API-Key header
        if not api_key:
            api_key = request.headers.get("X-API-Key", "")

        # Check query parameter
        if not api_key:
            api_key = request.query_params.get("api_key", "")

        if not api_key or not verify_api_key(api_key):
            return JSONResponse(
                {"error": "Unauthorized. Provide a valid API key."},
                status_code=401
            )

        return await call_next(request)


# ─── Routes ──────────────────────────────────────────────────────

sse = SseServerTransport("/messages")

async def handle_sse(request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())

async def handle_messages(request):
    await sse.handle_post_message(request.scope, request.receive, request._send)


async def health_check(request: Request):
    """Health check endpoint."""
    return JSONResponse({
        "status": "ok",
        "service": "jarvis-mcp",
        "tools_count": len(tool_mgr.tools)
    })


async def api_status(request: Request):
    """API status with tool list."""
    tools = [{"name": d["name"], "description": d["description"]}
             for d in tool_mgr.tools.values()]
    return JSONResponse({
        "status": "ok",
        "tools": tools
    })


async def api_execute(request: Request):
    """Direct REST API endpoint for executing tools (alternative to MCP)."""
    try:
        body = await request.json()
        tool_name = body.get("tool")
        arguments = body.get("arguments", {})

        if not tool_name:
            return JSONResponse({"error": "Missing 'tool' field"}, status_code=400)

        result = tool_mgr.execute_tool(tool_name, arguments)

        if isinstance(result, str):
            return JSONResponse({"success": True, "result": result})
        else:
            return JSONResponse({"success": True, "result": result})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── WebSocket Support ───────────────────────────────────────────

# Track connected WebSocket clients
_ws_clients = set()


async def ws_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time bidirectional communication.
    Protocol:
      Client sends: {"type": "execute", "tool": "...", "arguments": {...}}
      Server responds: {"type": "result", "success": true, "result": "..."}
      Server pushes: {"type": "event", "event": "tool_executed", "data": {...}}
    """
    # Auth check for WebSocket
    api_key = websocket.query_params.get("api_key", "")
    client_host = websocket.client.host if websocket.client else ""
    is_local = client_host in ("127.0.0.1", "::1", "localhost")

    if not is_local and not verify_api_key(api_key):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()
    _ws_clients.add(websocket)
    print(f"[MCP-WS] Client connected from {client_host}")

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "execute":
                tool_name = data.get("tool", "")
                arguments = data.get("arguments", {})

                try:
                    result = tool_mgr.execute_tool(tool_name, arguments)
                    await websocket.send_json({
                        "type": "result",
                        "success": True,
                        "tool": tool_name,
                        "result": str(result) if not isinstance(result, str) else result
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "result",
                        "success": False,
                        "tool": tool_name,
                        "error": str(e)
                    })

            elif msg_type == "list_tools":
                tools = [{"name": d["name"], "description": d["description"]}
                         for d in tool_mgr.tools.values()]
                await websocket.send_json({
                    "type": "tools_list",
                    "tools": tools
                })

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[MCP-WS] Error: {e}")
    finally:
        _ws_clients.discard(websocket)
        print(f"[MCP-WS] Client disconnected from {client_host}")


async def broadcast_event(event_type: str, data: dict):
    """Broadcast an event to all connected WebSocket clients."""
    message = {"type": "event", "event": event_type, "data": data}
    disconnected = set()
    for ws in _ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.add(ws)
    _ws_clients -= disconnected


# ─── Screen Sharing Endpoint ─────────────────────────────────────

async def screen_capture(request: Request):
    """
    Returns a JPEG screenshot of the current screen.
    Useful for mobile remote viewing.
    """
    try:
        import pyautogui
        from io import BytesIO

        img = pyautogui.screenshot()
        img = img.convert("RGB")
        img.thumbnail((800, 450))  # Smaller for mobile

        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=60)
        image_bytes = buffer.getvalue()

        return Response(content=image_bytes, media_type="image/jpeg")

    except Exception as e:
        return JSONResponse({"error": f"Screenshot failed: {e}"}, status_code=500)


async def screen_capture_base64(request: Request):
    """Returns a base64-encoded screenshot for embedding in JSON."""
    try:
        import pyautogui
        from io import BytesIO

        img = pyautogui.screenshot()
        img = img.convert("RGB")
        img.thumbnail((800, 450))

        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=60)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return JSONResponse({"image": f"data:image/jpeg;base64,{b64}"})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── Starlette App ───────────────────────────────────────────────

starlette_app = Starlette(
    debug=True,
    routes=[
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Route("/messages", endpoint=handle_messages, methods=["POST"]),
        Route("/health", endpoint=health_check, methods=["GET"]),
        Route("/api/status", endpoint=api_status, methods=["GET"]),
        Route("/api/execute", endpoint=api_execute, methods=["POST"]),
        Route("/api/screen", endpoint=screen_capture, methods=["GET"]),
        Route("/api/screen/base64", endpoint=screen_capture_base64, methods=["GET"]),
        WebSocketRoute("/ws", endpoint=ws_endpoint),
    ],
    middleware=[
        Middleware(APIKeyAuthMiddleware)
    ]
)


def start_mcp_server(port=8000):
    """Run the MCP server on the given port."""
    print(f"[JARVIS MCP] Starting MCP SSE server on port {port}...")
    print(f"[JARVIS MCP] Local: http://127.0.0.1:{port}")
    print(f"[JARVIS MCP] WebSocket: ws://127.0.0.1:{port}/ws")
    uvicorn.run(starlette_app, host="0.0.0.0", port=port, log_level="warning")
