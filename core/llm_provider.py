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
import threading
import requests
import subprocess as _subprocess
from typing import List, Dict, Any, Optional

logger = logging.getLogger("jarvis.llm")

# ─── Configuration ────────────────────────────────────────────────
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"

GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

# Anthropic Claude — the highest-quality provider, used for building/coding.
# Opus 4.8 is the most capable; override with ANTHROPIC_MODEL if desired.
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
ANTHROPIC_MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "8192"))
# When true, Claude is tried first for every request (not just build tasks).
PREFER_CLAUDE = os.environ.get("PREFER_CLAUDE", "false").lower() in ("true", "1", "yes")

# If True, NEVER fall back to local Ollama — protects GPU VRAM
PREFER_CLOUD_ONLY = os.environ.get("PREFER_CLOUD_ONLY", "false").lower() in ("true", "1", "yes")

# Connectivity check cache
_internet_cache = {"available": None, "checked_at": 0.0}
_CACHE_TTL = 30.0  # seconds

# Exponential backoff state for 429 retries
_backoff_state = {"consecutive_failures": 0, "last_backoff": 0.0}


def _unload_ollama_vram():
    """Force-unload all Ollama models from GPU VRAM to reclaim memory."""
    try:
        _subprocess.run(
            ["ollama", "stop", OLLAMA_MODEL],
            capture_output=True, timeout=5,
            creationflags=getattr(_subprocess, 'CREATE_NO_WINDOW', 0)
        )
        logger.info("[LLM] Unloaded Ollama model '%s' from VRAM (cloud is back online)", OLLAMA_MODEL)
    except Exception as e:
        logger.debug("[LLM] Could not unload Ollama model (may not be loaded): %s", e)


# ─── API Keys & Connectivity ─────────────────────────────────────


def _get_api_key() -> Optional[str]:
    """Get the Google API key from environment."""
    return os.environ.get("GOOGLE_API_KEY")


def _get_groq_api_key() -> Optional[str]:
    """Get the Groq API key from environment (free at console.groq.com)."""
    return os.environ.get("GROQ_API_KEY")


def _get_openrouter_api_key() -> Optional[str]:
    """Get the OpenRouter API key from environment (free at openrouter.ai)."""
    return os.environ.get("OPENROUTER_API_KEY")


def _get_anthropic_api_key() -> Optional[str]:
    """Get the Anthropic (Claude) API key from environment."""
    return os.environ.get("ANTHROPIC_API_KEY")


def has_claude() -> bool:
    """True if a Claude API key is configured."""
    return bool(_get_anthropic_api_key())


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

    # Check if we are in a penalty cooldown (cloud timed out recently)
    penalty_until = _internet_cache.get("penalty_until", 0)
    if now < penalty_until:
        return False

    try:
        # Quick connectivity check — list models endpoint
        resp = requests.get(
            f"{GEMINI_API_BASE}/models?key={api_key}",
            timeout=8
        )
        available = resp.status_code == 200
    except Exception:
        available = False

    _internet_cache["available"] = available
    _internet_cache["checked_at"] = now

    # Only log on state transitions to avoid terminal spam
    prev = _internet_cache.get("_prev_state")
    if prev != available:
        if available:
            logger.info("[LLM] Cloud available — using Gemini Flash")
            # Cloud is back! Unload Ollama from VRAM to reclaim GPU memory
            if prev is not None:  # Don't unload on first check (startup)
                threading.Thread(target=_unload_ollama_vram, daemon=True).start()
            _backoff_state["consecutive_failures"] = 0  # Reset backoff
        else:
            logger.info("[LLM] Cloud unavailable — using Local (Ollama)")
        _internet_cache["_prev_state"] = available

    return available


def get_provider_name() -> str:
    """Return the name of the currently active provider."""
    if _get_anthropic_api_key() and PREFER_CLAUDE:
        return f"Claude ({ANTHROPIC_MODEL})"
    claude_suffix = " + Claude (build)" if _get_anthropic_api_key() else ""
    if is_online():
        return f"Cloud (Gemini Flash){claude_suffix}"
    if _get_groq_api_key():
        return f"Cloud (Groq {GROQ_MODEL}){claude_suffix}"
    if _get_openrouter_api_key():
        return f"Cloud (OpenRouter){claude_suffix}"
    return f"Local (Ollama qwen2.5:7b){claude_suffix}"


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


# ─── Anthropic Claude Helpers ────────────────────────────────────

_anthropic_client = None


def _get_anthropic_client():
    """Lazily build a cached Anthropic SDK client."""
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=_get_anthropic_api_key())
    return _anthropic_client


def _convert_messages_to_anthropic(messages: List[Dict]) -> tuple:
    """Split Jarvis messages into (system_str, anthropic_messages).

    Anthropic takes the system prompt as a top-level arg, and message roles are
    only 'user'/'assistant'. System turns are merged into the system string.
    """
    system_parts: List[str] = []
    conv: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            if content:
                system_parts.append(str(content))
        else:
            conv.append({"role": "assistant" if role == "assistant" else "user",
                         "content": str(content)})
    # Anthropic requires the first message to be from the user.
    if not conv or conv[0]["role"] != "user":
        conv.insert(0, {"role": "user", "content": "(begin)"})
    return "\n\n".join(system_parts), conv


def _convert_tools_to_anthropic(tools: Optional[List[Dict]]) -> Optional[List[Dict]]:
    """Convert OpenAI-style tool schemas to Anthropic's {name, description, input_schema}."""
    if not tools:
        return None
    out = []
    for t in tools:
        fn = t.get("function", t)
        out.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return out


def _anthropic_chat(messages: List[Dict], tools: Optional[List[Dict]] = None,
                    temperature: float = 0.0, timeout: int = 120) -> Dict:
    """
    Call Claude via the official Anthropic SDK and return the Jarvis-standard
    {"content": str, "tool_calls": [{"function": {"name", "arguments"}}]} shape.

    NOTE: Opus 4.8 rejects `temperature` (400), so it is deliberately NOT sent.
    """
    client = _get_anthropic_client()
    system_str, conv = _convert_messages_to_anthropic(messages)
    kwargs: Dict[str, Any] = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "messages": conv,
    }
    if system_str:
        kwargs["system"] = system_str
    atools = _convert_tools_to_anthropic(tools)
    if atools:
        kwargs["tools"] = atools

    resp = client.with_options(timeout=float(timeout)).messages.create(**kwargs)

    result: Dict[str, Any] = {"content": "", "tool_calls": []}
    for block in resp.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            result["content"] += getattr(block, "text", "")
        elif btype == "tool_use":
            result["tool_calls"].append({
                "function": {
                    "name": getattr(block, "name", ""),
                    "arguments": getattr(block, "input", {}) or {},
                }
            })
    if not result["tool_calls"]:
        del result["tool_calls"]
    return result


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

    max_retries = 3
    data = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=body, timeout=timeout)
            if resp.status_code == 429:
                if attempt == max_retries:
                    resp.raise_for_status()
                wait = min(2.0 * attempt, 8.0)
                logger.warning("[LLM] Gemini API 429 Rate Limit (attempt %d/%d). Retrying in %.1fs...", attempt, max_retries, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        except requests.RequestException as e:
            if attempt == max_retries:
                raise e
            time.sleep(1.5)

    if not data:
        raise ConnectionError("Gemini API rate limit exceeded. Please wait a moment before trying again.")

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


def _gemini_vision_generate(prompt: str, image_base64: str,
                            temperature: float = 0.2, timeout: int = 60) -> str:
    """
    Multimodal Vision text generation via Gemini 1.5 Flash.
    """
    api_key = _get_api_key()
    if not api_key:
        raise ConnectionError("No GOOGLE_API_KEY")

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": image_base64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": temperature
        }
    }

    url = f"{GEMINI_API_BASE}/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    resp = requests.post(url, json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    
    candidates = data.get("candidates", [])
    if not candidates:
        return "No response from Gemini Vision."
        
    parts = candidates[0].get("content", {}).get("parts", [])
    result = ""
    for part in parts:
        if "text" in part:
            result += part["text"]
            
    return result


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


# ─── OpenAI-Compatible Helpers (Groq, OpenRouter, etc.) ──────────

def _openai_compat_chat(api_url: str, api_key: str, model: str,
                         messages: List[Dict], tools: Optional[List[Dict]] = None,
                         temperature: float = 0.0, timeout: int = 60,
                         extra_headers: Optional[Dict] = None) -> Dict:
    """
    Call any OpenAI-compatible chat completions API.
    Works with Groq, OpenRouter, Together AI, etc.
    Returns format: {"content": "...", "tool_calls": [...]}
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    if tools:
        openai_tools = []
        for t in tools:
            func = t.get("function", t)
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {})
                }
            })
        body["tools"] = openai_tools

    resp = requests.post(api_url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    result: Dict[str, Any] = {"content": message.get("content", "") or ""}

    tc_list = message.get("tool_calls", [])
    if tc_list:
        result["tool_calls"] = []
        for tc in tc_list:
            func = tc.get("function", {})
            args = func.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
            result["tool_calls"].append({
                "function": {
                    "name": func.get("name", ""),
                    "arguments": args
                }
            })

    return result


def _openai_compat_generate(api_url: str, api_key: str, model: str,
                             prompt: str, temperature: float = 0.0,
                             timeout: int = 60, max_tokens: int = 500,
                             extra_headers: Optional[Dict] = None) -> str:
    """Simple text generation via any OpenAI-compatible API."""
    result = _openai_compat_chat(
        api_url, api_key, model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature, timeout=timeout,
        extra_headers=extra_headers)
    return result.get("content", "")


def _openai_compat_chat_stream(api_url: str, api_key: str, model: str,
                                messages: List[Dict],
                                tools: Optional[List[Dict]] = None,
                                temperature: float = 0.0, timeout: int = 60,
                                extra_headers: Optional[Dict] = None):
    """Stream from any OpenAI-compatible chat completions API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True
    }

    resp = requests.post(api_url, headers=headers, json=body, timeout=timeout, stream=True)
    resp.raise_for_status()

    for line in resp.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8")
        if line_str.startswith("data: "):
            data_str = line_str[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                delta = data.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content
            except json.JSONDecodeError:
                pass


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
    """
    if is_online():
        try:
            cloud_timeout = min(timeout, 45)
            yield from _gemini_chat_stream(messages, tools, temperature, cloud_timeout)
            return
        except Exception as e:
            logger.warning("[LLM] Cloud stream failed (%s), falling back to local", e)
            _internet_cache["available"] = False
            n = _backoff_state["consecutive_failures"] + 1
            _backoff_state["consecutive_failures"] = n
            penalty = min(30 * (2 ** (n - 1)), 120.0)
            _internet_cache["penalty_until"] = time.time() + penalty

    # ── Groq (free, ultra-fast LPU inference) ────────────────────
    groq_key = _get_groq_api_key()
    if groq_key:
        try:
            yield from _openai_compat_chat_stream(
                GROQ_API_URL, groq_key, GROQ_MODEL,
                messages, tools, temperature, min(timeout, 30))
            return
        except Exception as e:
            logger.warning("[LLM] Groq stream failed (%s), trying next provider", e)

    # ── OpenRouter (free community models) ───────────────────────
    or_key = _get_openrouter_api_key()
    if or_key:
        try:
            yield from _openai_compat_chat_stream(
                OPENROUTER_API_URL, or_key, OPENROUTER_MODEL,
                messages, tools, temperature, min(timeout, 30),
                extra_headers={"HTTP-Referer": "https://jarvis-assistant.local",
                               "X-Title": "J.A.R.V.I.S."})
            return
        except Exception as e:
            logger.warning("[LLM] OpenRouter stream failed (%s), trying next provider", e)

    # Cloud-only mode: never touch Ollama / VRAM
    if PREFER_CLOUD_ONLY:
        logger.warning("[LLM] PREFER_CLOUD_ONLY=true — not falling back to Ollama for stream")
        yield "Cloud is temporarily busy. Please try again in a moment."
        return

    # Local fallback
    try:
        yield from _ollama_chat_stream(messages, tools, temperature, timeout)
    except Exception as e:
        logger.error("[LLM] Both cloud and local stream failed: %s", e)
        yield f"LLM stream failed: {e}"

# ─── Public API ──────────────────────────────────────────────────

def llm_chat(messages: List[Dict], tools: Optional[List[Dict]] = None,
             temperature: float = 0.0, timeout: int = 60,
             prefer: Optional[str] = None) -> Dict:
    """
    Send a chat completion request to the best available LLM:
    0. Anthropic Claude (highest quality — if ANTHROPIC_API_KEY and preferred)
    1. Google Gemini Flash (free — if GOOGLE_API_KEY present and online)
    2. Groq (free — if GROQ_API_KEY present)
    3. OpenRouter (free — if OPENROUTER_API_KEY present)
    4. Local Ollama (qwen2.5:7b)

    Set ``prefer="anthropic"`` (or env PREFER_CLAUDE=true) to route to Claude
    first — used for building/coding, where quality matters most. Claude
    failures fall through to the free providers below.
    """
    # ── Anthropic Claude (opt-in: coding/build tasks) ────────────
    if _get_anthropic_api_key() and (prefer == "anthropic" or PREFER_CLAUDE):
        try:
            result = _anthropic_chat(messages, tools, temperature, max(timeout, 120))
            logger.debug("[LLM] Claude call succeeded")
            return result
        except Exception as e:
            logger.warning("[LLM] Claude call failed (%s), falling back to other providers", e)

    api_key = _get_api_key()
    if api_key:
        try:
            cloud_timeout = max(timeout, 45)
            result = _gemini_chat(messages, tools, temperature, cloud_timeout)
            logger.debug("[LLM] Cloud call succeeded")
            _backoff_state["consecutive_failures"] = 0
            _internet_cache["available"] = True
            return result
        except Exception as e:
            logger.warning("[LLM] Cloud call failed (%s), attempting local fallback", e)

    # ── Groq (free, ultra-fast LPU inference) ────────────────────
    groq_key = _get_groq_api_key()
    if groq_key:
        try:
            result = _openai_compat_chat(
                GROQ_API_URL, groq_key, GROQ_MODEL,
                messages, tools, temperature, min(timeout, 30))
            logger.debug("[LLM] Groq chat call succeeded")
            return result
        except Exception as e:
            logger.warning("[LLM] Groq chat failed (%s), trying next provider", e)

    # ── OpenRouter (free community models) ───────────────────────
    or_key = _get_openrouter_api_key()
    if or_key:
        try:
            result = _openai_compat_chat(
                OPENROUTER_API_URL, or_key, OPENROUTER_MODEL,
                messages, tools, temperature, min(timeout, 30),
                extra_headers={"HTTP-Referer": "https://jarvis-assistant.local",
                               "X-Title": "J.A.R.V.I.S."})
            logger.debug("[LLM] OpenRouter chat call succeeded")
            return result
        except Exception as e:
            logger.warning("[LLM] OpenRouter chat failed (%s), trying next provider", e)

    # Cloud-only mode: never touch Ollama / VRAM
    if PREFER_CLOUD_ONLY:
        logger.warning("[LLM] PREFER_CLOUD_ONLY=true — not falling back to Ollama")
        return {"content": "I'm temporarily unable to reach the AI cloud server. Please check your internet connection, sir.",
                "provider_error": True}

    # Local fallback
    try:
        result = _ollama_chat(messages, tools, temperature, timeout)
        logger.debug("[LLM] Local Ollama call succeeded")
        _internet_cache["available"] = False
        _internet_cache["penalty_until"] = time.time() + 30.0
        return result
    except Exception as e:
        logger.error("[LLM] Both cloud and local LLM failed: %s", e)
        _internet_cache["available"] = None
        _internet_cache["penalty_until"] = 0
        # Flag so agentic callers can distinguish a provider failure from a real
        # answer and retry, instead of surfacing this as the final response.
        return {"content": "I'm temporarily unable to connect to the AI server. Please check your internet connection and try again, sir.",
                "provider_error": True}


def llm_generate(prompt: str, temperature: float = 0.0,
                 timeout: int = 60, max_tokens: int = 500) -> str:
    """
    Simple text generation from the best available LLM.
    """
    api_key = _get_api_key()
    if api_key:
        try:
            cloud_timeout = max(timeout, 45)
            result = _gemini_generate(prompt, temperature=temperature,
                                      timeout=cloud_timeout, max_tokens=max_tokens)
            logger.debug("[LLM] Cloud generate succeeded")
            _backoff_state["consecutive_failures"] = 0
            _internet_cache["available"] = True
            return result
        except Exception as e:
            logger.warning("[LLM] Cloud generate failed (%s), attempting local fallback", e)

    # ── Groq (free, ultra-fast LPU inference) ────────────────────
    groq_key = _get_groq_api_key()
    if groq_key:
        try:
            result = _openai_compat_generate(
                GROQ_API_URL, groq_key, GROQ_MODEL,
                prompt, temperature=temperature, timeout=min(timeout, 30))
            logger.debug("[LLM] Groq generate call succeeded")
            return result
        except Exception as e:
            logger.warning("[LLM] Groq generate failed (%s), trying next provider", e)

    # ── OpenRouter (free community models) ───────────────────────
    or_key = _get_openrouter_api_key()
    if or_key:
        try:
            result = _openai_compat_generate(
                OPENROUTER_API_URL, or_key, OPENROUTER_MODEL,
                prompt, temperature=temperature, timeout=min(timeout, 30),
                extra_headers={"HTTP-Referer": "https://jarvis-assistant.local",
                               "X-Title": "J.A.R.V.I.S."})
            logger.debug("[LLM] OpenRouter generate call succeeded")
            return result
        except Exception as e:
            logger.warning("[LLM] OpenRouter generate failed (%s), trying next provider", e)

    # Cloud-only mode: never touch Ollama / VRAM
    if PREFER_CLOUD_ONLY:
        logger.warning("[LLM] PREFER_CLOUD_ONLY=true — not falling back to Ollama")
        return "I'm temporarily unable to reach the AI cloud server. Please check your internet connection, sir."

    # Local fallback
    try:
        result = _ollama_generate(prompt, temperature=temperature,
                                  timeout=timeout, max_tokens=max_tokens)
        logger.debug("[LLM] Local Ollama generate succeeded")
        _internet_cache["available"] = False
        _internet_cache["penalty_until"] = time.time() + 30.0
        return result
    except Exception as e:
        logger.error("[LLM] Both cloud and local generate failed: %s", e)
        _internet_cache["available"] = None
        _internet_cache["penalty_until"] = 0
        return "I'm temporarily unable to connect to the AI server. Please check your internet connection and try again, sir."

def llm_vision_generate(prompt: str, image_base64: str,
                        temperature: float = 0.2, timeout: int = 60) -> str:
    """
    Multimodal Vision generation. Attempts Gemini 1.5 Flash first,
    falls back to local Qwen2.5-VL if offline.
    """
    api_key = _get_api_key()
    if api_key and is_online():
        try:
            cloud_timeout = max(timeout, 45)
            result = _gemini_vision_generate(prompt, image_base64, temperature=temperature, timeout=cloud_timeout)
            logger.debug("[LLM] Cloud Vision generate succeeded")
            _backoff_state["consecutive_failures"] = 0
            return result
        except Exception as e:
            logger.warning("[LLM] Cloud Vision generate failed (%s), attempting local fallback", e)

    if PREFER_CLOUD_ONLY:
        logger.warning("[LLM] PREFER_CLOUD_ONLY=true — not falling back to Ollama")
        return "I'm temporarily unable to reach the AI cloud server for vision analysis."

    # Local fallback to Qwen2.5-VL
    try:
        payload = {
            "model": "qwen2.5vl:3b",
            "prompt": prompt,
            "images": [image_base64],
            "stream": False,
            "options": {"temperature": temperature}
        }
        resp = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        logger.debug("[LLM] Local Ollama Vision generate succeeded")
        return resp.json().get("response", "")
    except Exception as e:
        logger.error("[LLM] Both cloud and local vision generate failed: %s", e)
        return "I'm temporarily unable to analyze images. Please check your internet connection and ensure Ollama is running."
