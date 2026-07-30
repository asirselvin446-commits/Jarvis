"""
J.A.R.V.I.S. LLM Provider
═══════════════════════════
Centralized LLM routing with automatic cloud/local switching.

When internet is available → Google Gemini Flash (fast, free tier)
When offline             → Local Ollama (qwen2.5:7b)

If a cloud call fails, it automatically retries with local Ollama.
"""

import os
import time
import json
import logging
import requests
from typing import List, Dict, Any, Optional

logger = logging.getLogger("jarvis.llm")

# ─── Configuration ────────────────────────────────────────────────
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Connectivity check cache
_internet_cache = {"available": None, "checked_at": 0.0}
_CACHE_TTL = 30.0  # seconds


# ─── Internet Check ──────────────────────────────────────────────

def _get_api_key() -> Optional[str]:
    """Get the Google API key from environment."""
    return os.environ.get("GOOGLE_API_KEY")


def is_online() -> bool:
    """
    Check if internet is available and a valid API key exists.
    Result is cached for 30 seconds to avoid spamming.
    """
    now = time.time()
    if (now - _internet_cache["checked_at"]) < _CACHE_TTL and _internet_cache["available"] is not None:
        return _internet_cache["available"]

    api_key = _get_api_key()
    if not api_key:
        logger.info("[LLM] No GOOGLE_API_KEY set — using Local (Ollama)")
        _internet_cache["available"] = False
        _internet_cache["checked_at"] = now
        return False

    try:
        # Quick connectivity check — list models endpoint
        resp = requests.get(
            f"{GEMINI_API_BASE}/models?key={api_key}",
            timeout=3
        )
        available = resp.status_code == 200
    except Exception:
        available = False

    _internet_cache["available"] = available
    _internet_cache["checked_at"] = now

    if available:
        logger.info("[LLM] Cloud available — using Gemini Flash")
    else:
        logger.info("[LLM] Cloud unavailable — using Local (Ollama)")

    return available


def get_provider_name() -> str:
    """Return the name of the currently active provider."""
    return "Cloud (Gemini Flash)" if is_online() else "Local (Ollama qwen2.5:7b)"


# ─── Gemini API Helpers ──────────────────────────────────────────

def _convert_messages_to_gemini(messages: List[Dict]) -> tuple:
    """
    Convert Ollama-style messages to Gemini API format.
    Returns (system_instruction, contents).
    
    Ollama format:  [{"role": "system"|"user"|"assistant", "content": "..."}]
    Gemini format:  system_instruction + contents with "user"|"model" roles
    """
    system_parts = []
    contents = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            system_parts.append(content)
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})

    system_instruction = "\n\n".join(system_parts) if system_parts else None
    return system_instruction, contents


def _convert_tools_to_gemini(tools: List[Dict]) -> Optional[List[Dict]]:
    """
    Convert Ollama-style tool schemas to Gemini function declarations.
    
    Ollama format:  [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]
    Gemini format:  [{"function_declarations": [{"name": ..., "description": ..., "parameters": ...}]}]
    """
    if not tools:
        return None

    declarations = []
    for tool in tools:
        func = tool.get("function", tool)  # Handle both wrapped and unwrapped
        decl = {
            "name": func.get("name", ""),
            "description": func.get("description", ""),
        }
        params = func.get("parameters", {})
        if params:
            # Clean up the parameters — Gemini is strict about JSON schema
            clean_params = _clean_params_for_gemini(params)
            if clean_params:
                decl["parameters"] = clean_params
        declarations.append(decl)

    return [{"function_declarations": declarations}] if declarations else None


def _clean_params_for_gemini(params: dict) -> dict:
    """
    Clean parameter schema for Gemini compatibility.
    Removes unsupported fields like 'default' and ensures valid types.
    """
    cleaned = {}
    if "type" in params:
        cleaned["type"] = params["type"].upper() if params["type"] in (
            "string", "number", "integer", "boolean", "array", "object"
        ) else params["type"]
    
    if "properties" in params:
        cleaned_props = {}
        for k, v in params["properties"].items():
            prop = {"type": v.get("type", "string").upper()}
            if "description" in v:
                prop["description"] = v["description"]
            if "enum" in v:
                prop["enum"] = v["enum"]
            if "items" in v:
                prop["items"] = _clean_params_for_gemini(v["items"])
            cleaned_props[k] = prop
        cleaned["properties"] = cleaned_props
    
    if "required" in params:
        cleaned["required"] = params["required"]
    
    return cleaned


def _gemini_chat(messages: List[Dict], tools: Optional[List[Dict]] = None,
                 temperature: float = 0.0, timeout: int = 60) -> Dict:
    """
    Call Gemini API using REST (no SDK dependency needed).
    Returns a dict in Ollama-compatible format: {"content": "...", "tool_calls": [...]}
    """
    api_key = _get_api_key()
    if not api_key:
        raise ConnectionError("No GOOGLE_API_KEY")

    system_instruction, contents = _convert_messages_to_gemini(messages)

    # Build request body
    body: Dict[str, Any] = {"contents": contents}

    if system_instruction:
        body["system_instruction"] = {"parts": [{"text": system_instruction}]}

    gemini_tools = _convert_tools_to_gemini(tools) if tools else None
    if gemini_tools:
        body["tools"] = gemini_tools

    body["generationConfig"] = {
        "temperature": temperature,
    }

    url = f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={api_key}"

    resp = requests.post(url, json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    # Parse Gemini response into Ollama-compatible format
    result = {"content": "", "tool_calls": []}

    candidates = data.get("candidates", [])
    if not candidates:
        result["content"] = "No response from Gemini."
        return result

    parts = candidates[0].get("content", {}).get("parts", [])

    for part in parts:
        if "text" in part:
            result["content"] += part["text"]
        elif "functionCall" in part:
            fc = part["functionCall"]
            result["tool_calls"].append({
                "function": {
                    "name": fc.get("name", ""),
                    "arguments": fc.get("args", {})
                }
            })

    if not result["tool_calls"]:
        del result["tool_calls"]

    return result


def _gemini_generate(prompt: str, system: str = "",
                     temperature: float = 0.0, timeout: int = 60,
                     max_tokens: int = 500) -> str:
    """
    Simple text generation via Gemini (equivalent to Ollama /api/generate).
    Returns just the response text.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    result = _gemini_chat(messages, temperature=temperature, timeout=timeout)
    return result.get("content", "")


# ─── Ollama Helpers ──────────────────────────────────────────────

def _ollama_chat(messages: List[Dict], tools: Optional[List[Dict]] = None,
                 temperature: float = 0.0, timeout: int = 60) -> Dict:
    """
    Call local Ollama /api/chat endpoint.
    Returns the message dict from Ollama's response.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature}
    }
    if tools:
        payload["tools"] = tools

    resp = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("message", {})


def _ollama_generate(prompt: str, temperature: float = 0.0,
                     timeout: int = 60, max_tokens: int = 500) -> str:
    """
    Call local Ollama /api/generate endpoint.
    Returns the response text.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens}
    }

    resp = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("response", "")


# ─── Streaming Helpers ───────────────────────────────────────────

def _gemini_chat_stream(messages: List[Dict], tools: Optional[List[Dict]] = None,
                        temperature: float = 0.0, timeout: int = 60):
    """
    Call Gemini API using streamGenerateContent with alt=sse.
    Yields chunks of generated text.
    """
    api_key = _get_api_key()
    if not api_key:
        raise ConnectionError("No GOOGLE_API_KEY")

    system_instruction, contents = _convert_messages_to_gemini(messages)
    body: Dict[str, Any] = {"contents": contents}
    if system_instruction:
        body["system_instruction"] = {"parts": [{"text": system_instruction}]}
    
    gemini_tools = _convert_tools_to_gemini(tools) if tools else None
    if gemini_tools:
        body["tools"] = gemini_tools

    body["generationConfig"] = {"temperature": temperature}

    url = f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:streamGenerateContent?key={api_key}&alt=sse"

    resp = requests.post(url, json=body, timeout=timeout, stream=True)
    resp.raise_for_status()
    
    # Parse SSE format
    for line in resp.iter_lines():
        if not line:
            continue
        line_str = line.decode('utf-8')
        if line_str.startswith("data: "):
            data_str = line_str[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for part in parts:
                        if "text" in part:
                            yield part["text"]
            except json.JSONDecodeError:
                pass


def _ollama_chat_stream(messages: List[Dict], tools: Optional[List[Dict]] = None,
                        temperature: float = 0.0, timeout: int = 60):
    """
    Call local Ollama /api/chat endpoint with stream=True.
    Yields chunks of generated text.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature}
    }
    if tools:
        payload["tools"] = tools

    resp = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=timeout, stream=True)
    resp.raise_for_status()
    
    for line in resp.iter_lines():
        if line:
            try:
                data = json.loads(line)
                if "message" in data and "content" in data["message"]:
                    yield data["message"]["content"]
            except json.JSONDecodeError:
                pass

def llm_chat_stream(messages: List[Dict], tools: Optional[List[Dict]] = None,
                    temperature: float = 0.0, timeout: int = 60):
    """
    Send a chat completion request to the best available LLM and yield chunks.
    Note: Tool calls are not easily streamable, so this is best for text generation.
    """
    if is_online():
        try:
            yield from _gemini_chat_stream(messages, tools, temperature, timeout)
            return
        except Exception as e:
            logger.warning("[LLM] Cloud stream failed (%s), falling back to local", e)
            _internet_cache["available"] = None

    # Local fallback
    try:
        yield from _ollama_chat_stream(messages, tools, temperature, timeout)
    except Exception as e:
        logger.error("[LLM] Both cloud and local stream failed: %s", e)
        yield f"LLM stream failed: {e}"

# ─── Public API ──────────────────────────────────────────────────

def llm_chat(messages: List[Dict], tools: Optional[List[Dict]] = None,
             temperature: float = 0.0, timeout: int = 60) -> Dict:
    """
    Send a chat completion request to the best available LLM.
    
    Args:
        messages: List of {"role": "system"|"user"|"assistant", "content": "..."}
        tools: Optional Ollama-format tool schemas
        temperature: Sampling temperature
        timeout: Request timeout in seconds
    
    Returns:
        Dict with "content" (str) and optionally "tool_calls" (list).
        On complete failure, returns {"content": "LLM call failed: <error>"}
    """
    if is_online():
        try:
            result = _gemini_chat(messages, tools, temperature, timeout)
            logger.debug("[LLM] Cloud call succeeded")
            return result
        except Exception as e:
            logger.warning("[LLM] Cloud call failed (%s), falling back to local Ollama", e)
            # Invalidate cache so next call re-checks
            _internet_cache["available"] = None

    # Local fallback
    try:
        result = _ollama_chat(messages, tools, temperature, timeout)
        logger.debug("[LLM] Local Ollama call succeeded")
        return result
    except Exception as e:
        logger.error("[LLM] Both cloud and local LLM failed: %s", e)
        return {"content": f"LLM call failed: {e}"}


def llm_generate(prompt: str, temperature: float = 0.0,
                 timeout: int = 60, max_tokens: int = 500) -> str:
    """
    Simple text generation from the best available LLM.
    
    Args:
        prompt: The prompt text
        temperature: Sampling temperature
        timeout: Request timeout in seconds
        max_tokens: Maximum tokens to generate
    
    Returns:
        The generated text. On failure, returns an error string.
    """
    if is_online():
        try:
            result = _gemini_generate(prompt, temperature=temperature,
                                      timeout=timeout, max_tokens=max_tokens)
            logger.debug("[LLM] Cloud generate succeeded")
            return result
        except Exception as e:
            logger.warning("[LLM] Cloud generate failed (%s), falling back to local Ollama", e)
            _internet_cache["available"] = None

    # Local fallback
    try:
        result = _ollama_generate(prompt, temperature=temperature,
                                  timeout=timeout, max_tokens=max_tokens)
        logger.debug("[LLM] Local Ollama generate succeeded")
        return result
    except Exception as e:
        logger.error("[LLM] Both cloud and local generate failed: %s", e)
        return f"LLM call failed: {e}"
