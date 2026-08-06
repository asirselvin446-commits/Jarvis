"""
Dual-Model LLM Provider for Jarvis
Intelligently switches between cloud (Gemini) and local (Ollama) models.
Includes caching, fallback, and cost optimization.
"""

import os
import json
import logging
import hashlib
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
import requests

logger = logging.getLogger(__name__)

# Model configuration
CLOUD_API_KEY = os.getenv("GOOGLE_API_KEY")
CLOUD_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

LOCAL_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LOCAL_MODEL = "qwen2.5:7b"

# Cache configuration
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".jarvis", "llm_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL_HOURS = 24


class ModelType(Enum):
    """Available model types."""
    CLOUD = "cloud"  # Gemini Flash (via REST API)
    LOCAL = "local"  # Ollama Qwen2.5
    AUTO = "auto"    # Automatic selection


class LLMMetrics:
    """Track LLM usage metrics."""
    
    def __init__(self):
        self.cloud_calls = 0
        self.local_calls = 0
        self.cached_calls = 0
        self.fallback_count = 0
        self.total_latency_ms = 0.0
        self.cache_hits = 0
        self.start_time = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cloud_calls": self.cloud_calls,
            "local_calls": self.local_calls,
            "cached_calls": self.cached_calls,
            "fallback_count": self.fallback_count,
            "cache_hit_rate": round(
                (self.cache_hits / (self.cloud_calls + self.local_calls) * 100)
                if (self.cloud_calls + self.local_calls) > 0 else 0,
                2
            ),
            "avg_latency_ms": round(
                self.total_latency_ms / (self.cloud_calls + self.local_calls)
                if (self.cloud_calls + self.local_calls) > 0 else 0,
                2
            ),
            "uptime_hours": round(
                (datetime.now() - self.start_time).total_seconds() / 3600,
                2
            ),
        }


class DualModelLLMProvider:
    """
    Intelligent LLM provider that:
    - Switches between cloud (Gemini) and local (Ollama) models
    - Caches responses for repeated queries
    - Handles fallback gracefully
    - Optimizes for cost and performance
    """
    
    def __init__(self):
        self.cloud_available = self._check_cloud_availability()
        self.local_available = self._check_local_availability()
        self.metrics = LLMMetrics()
        self.request_cache: Dict[str, Tuple[str, datetime]] = {}
    
    def _check_cloud_availability(self) -> bool:
        """Check if cloud API is available."""
        if not CLOUD_API_KEY:
            logger.warning("GOOGLE_API_KEY not set - cloud model unavailable")
            return False
        
        try:
            # Test with minimal request
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{"parts": [{"text": "test"}]}],
                "generationConfig": {"maxOutputTokens": 10}
            }
            
            response = requests.post(
                f"{CLOUD_URL}?key={CLOUD_API_KEY}",
                json=data,
                headers=headers,
                timeout=5
            )
            
            available = response.status_code == 200
            logger.info(f"Cloud model availability: {available}")
            return available
        except Exception as e:
            logger.warning(f"Cloud model check failed: {e}")
            return False
    
    def _check_local_availability(self) -> bool:
        """Check if local Ollama is available."""
        try:
            response = requests.get(
                f"{LOCAL_OLLAMA_URL}/api/tags",
                timeout=2
            )
            
            available = response.status_code == 200
            logger.info(f"Local model availability: {available}")
            return available
        except Exception as e:
            logger.warning(f"Local model check failed: {e}")
            return False
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        model_type: ModelType = ModelType.AUTO,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: List[Dict] = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """
        Send a chat request to the LLM.
        
        Args:
            messages: Chat history
            model_type: Cloud, Local, or Auto
            temperature: Sampling temperature
            max_tokens: Maximum output tokens
            tools: Available tools for function calling
            timeout: Request timeout
            
        Returns:
            LLM response with choices and metadata
        """
        start_time = time.time()
        
        # Check cache
        cache_key = self._get_cache_key(messages)
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            self.metrics.cached_calls += 1
            self.metrics.cache_hits += 1
            logger.info("Cache hit for LLM request")
            return cached_response
        
        # Select model
        if model_type == ModelType.AUTO:
            model_type = self._select_model(messages)
        
        # Call LLM
        try:
            if model_type == ModelType.CLOUD:
                response = self._call_cloud_llm(
                    messages, temperature, max_tokens, tools, timeout
                )
                self.metrics.cloud_calls += 1
            else:
                response = self._call_local_llm(
                    messages, temperature, max_tokens, tools, timeout
                )
                self.metrics.local_calls += 1
            
            # Cache successful response
            if response.get("success"):
                self._cache_response(cache_key, response)
            
        except Exception as e:
            logger.error(f"LLM call failed ({model_type.value}): {e}")
            self.metrics.fallback_count += 1
            
            # Try fallback
            fallback_type = (
                ModelType.LOCAL if model_type == ModelType.CLOUD
                else ModelType.CLOUD
            )
            
            try:
                response = self.chat(
                    messages,
                    model_type=fallback_type,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    timeout=timeout
                )
                logger.info(f"Fallback to {fallback_type.value} succeeded")
            except Exception as fallback_error:
                logger.error(f"Both models failed: {fallback_error}")
                response = {
                    "success": False,
                    "error": str(fallback_error),
                }
        
        # Update metrics
        duration_ms = (time.time() - start_time) * 1000
        self.metrics.total_latency_ms += duration_ms
        response["duration_ms"] = duration_ms
        response["model"] = model_type.value
        
        return response
    
    def _select_model(self, messages: List[Dict]) -> ModelType:
        """
        Intelligently select model based on:
        - Availability
        - Query complexity
        - Internet connectivity
        - Cost optimization
        """
        # Check connectivity
        if not self._has_internet():
            return ModelType.LOCAL if self.local_available else ModelType.CLOUD
        
        # Analyze complexity
        complexity = self._estimate_complexity(messages)
        
        # Simple queries: prefer local (fast, free)
        if complexity < 3:
            if self.local_available:
                return ModelType.LOCAL
            return ModelType.CLOUD if self.cloud_available else ModelType.LOCAL
        
        # Complex queries: prefer cloud (more capable)
        if complexity > 7:
            if self.cloud_available:
                return ModelType.CLOUD
            return ModelType.LOCAL if self.local_available else ModelType.CLOUD
        
        # Medium: prefer available and fast
        if self.cloud_available:
            return ModelType.CLOUD
        return ModelType.LOCAL if self.local_available else ModelType.CLOUD
    
    def _call_cloud_llm(
        self,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        tools: List[Dict],
        timeout: int,
    ) -> Dict[str, Any]:
        """Call Gemini Flash via REST API."""
        headers = {"Content-Type": "application/json"}
        
        # Convert messages to Gemini format
        contents = []
        for msg in messages:
            contents.append({
                "role": "user" if msg["role"] == "user" else "model",
                "parts": [{"text": msg["content"]}]
            })
        
        data = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }
        
        # Add tools if provided
        if tools:
            data["tools"] = [{"functionDeclarations": tools}]
        
        response = requests.post(
            f"{CLOUD_URL}?key={CLOUD_API_KEY}",
            json=data,
            headers=headers,
            timeout=timeout
        )
        
        if response.status_code != 200:
            raise Exception(f"Cloud API error: {response.status_code} {response.text}")
        
        result = response.json()
        
        # Extract response
        try:
            candidates = result.get("candidates", [])
            if not candidates:
                raise Exception("No candidates in response")
            
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            
            # Check for tool calls
            if any("functionCall" in part for part in parts):
                tool_calls = [part["functionCall"] for part in parts if "functionCall" in part]
                return {
                    "success": True,
                    "tool_calls": tool_calls,
                }
            
            # Regular text response
            text = " ".join([part.get("text", "") for part in parts if "text" in part])
            return {
                "success": True,
                "response": text,
                "choices": [{"message": {"content": text}}],
            }
        except Exception as e:
            logger.error(f"Failed to parse cloud response: {e}")
            raise
    
    def _call_local_llm(
        self,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        tools: List[Dict],
        timeout: int,
    ) -> Dict[str, Any]:
        """Call Ollama Qwen2.5 model."""
        # Build prompt from messages
        prompt = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in messages
        ])
        
        data = {
            "model": LOCAL_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        
        response = requests.post(
            f"{LOCAL_OLLAMA_URL}/api/generate",
            json=data,
            timeout=timeout
        )
        
        if response.status_code != 200:
            raise Exception(f"Ollama error: {response.status_code}")
        
        result = response.json()
        text = result.get("response", "")
        
        return {
            "success": True,
            "response": text,
            "choices": [{"message": {"content": text}}],
        }
    
    def _get_cache_key(self, messages: List[Dict]) -> str:
        """Generate cache key for messages."""
        content = json.dumps(messages, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_cached_response(self, cache_key: str) -> Optional[Dict]:
        """Get cached response if available and not expired."""
        if cache_key not in self.request_cache:
            return None
        
        response, cached_time = self.request_cache[cache_key]
        
        # Check TTL
        if datetime.now() - cached_time > timedelta(hours=CACHE_TTL_HOURS):
            del self.request_cache[cache_key]
            return None
        
        return json.loads(response)
    
    def _cache_response(self, cache_key: str, response: Dict):
        """Cache a response."""
        try:
            self.request_cache[cache_key] = (
                json.dumps(response),
                datetime.now()
            )
            
            # Limit cache size
            if len(self.request_cache) > 1000:
                # Remove oldest entries
                oldest_key = min(
                    self.request_cache.keys(),
                    key=lambda k: self.request_cache[k][1]
                )
                del self.request_cache[oldest_key]
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")
    
    def _has_internet(self) -> bool:
        """Check if internet is available."""
        try:
            requests.head("https://www.google.com", timeout=2)
            return True
        except:
            return False
    
    def _estimate_complexity(self, messages: List[Dict]) -> float:
        """
        Estimate query complexity (0-10).
        Higher = more complex query.
        """
        total_tokens = sum(len(msg.get("content", "").split()) for msg in messages)
        
        score = 0.0
        
        # Complexity by token count
        if total_tokens < 50:
            score += 1.0
        elif total_tokens < 200:
            score += 3.0
        else:
            score += 5.0
        
        # Complexity by content
        content = " ".join([m.get("content", "") for m in messages])
        
        if any(word in content.lower() for word in ["complex", "explain", "analyze", "debug"]):
            score += 2.0
        if any(word in content.lower() for word in ["code", "python", "javascript"]):
            score += 1.5
        if any(word in content.lower() for word in ["calculate", "math", "algorithm"]):
            score += 2.0
        
        return min(score, 10.0)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get usage metrics."""
        return self.metrics.to_dict()
    
    def reset_metrics(self):
        """Reset usage metrics."""
        self.metrics = LLMMetrics()


# Global provider instance
_provider = None


def get_dual_model_provider() -> DualModelLLMProvider:
    """Get or create global provider instance."""
    global _provider
    if _provider is None:
        _provider = DualModelLLMProvider()
    return _provider
