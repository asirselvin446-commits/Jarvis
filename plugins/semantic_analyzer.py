"""
Example Advanced Plugin for J.A.R.V.I.S
Demonstrates the new plugin system with semantic analysis.
"""

import logging
import requests
from typing import List, Dict, Any
from core.tool_manager import tool
from core.advanced_integration import jarvis_tool

logger = logging.getLogger(__name__)


class SemanticAnalyzerPlugin:
    """
    Example plugin that performs semantic analysis on text.
    Shows how to use the new plugin system effectively.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.api_url = self.config.get("api_url", "http://localhost:11434")
        self.model = self.config.get("model", "llama2")
        logger.info(f"SemanticAnalyzerPlugin initialized with model: {self.model}")
    
    def cleanup(self):
        """Called when plugin is unloaded"""
        logger.info("SemanticAnalyzerPlugin cleanup")
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of text."""
        prompt = f"""Analyze the sentiment of this text and provide:
1. Overall sentiment (positive/negative/neutral)
2. Confidence score (0-1)
3. Key emotional words
4. Brief explanation

Text: {text}

Respond in JSON format."""
        
        try:
            response = requests.post(
                f"{self.api_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json().get("response", "")
                return {
                    "success": True,
                    "analysis": result
                }
            else:
                return {
                    "success": False,
                    "error": f"API error: {response.status_code}"
                }
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def extract_keywords(self, text: str, top_k: int = 10) -> List[str]:
        """Extract important keywords from text."""
        prompt = f"""Extract the top {top_k} most important keywords from this text.
Return only the keywords as a comma-separated list, no explanations.

Text: {text}"""
        
        try:
            response = requests.post(
                f"{self.api_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json().get("response", "")
                keywords = [kw.strip() for kw in result.split(",")]
                return keywords[:top_k]
            else:
                return []
        except Exception as e:
            logger.error(f"Keyword extraction failed: {e}")
            return []


# Create plugin instance
_plugin = SemanticAnalyzerPlugin()


# Define tools as functions decorated with @tool
@tool(
    name="analyze_text_sentiment",
    description="Analyze the sentiment of text (positive, negative, or neutral)",
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to analyze"
            }
        },
        "required": ["text"]
    }
)
def analyze_sentiment(text: str) -> Dict[str, Any]:
    """Analyze sentiment of provided text."""
    return _plugin.analyze_sentiment(text)


@tool(
    name="extract_text_keywords",
    description="Extract important keywords from text using AI analysis",
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to analyze"
            },
            "top_k": {
                "type": "integer",
                "description": "Number of keywords to extract (default: 10)",
                "default": 10
            }
        },
        "required": ["text"]
    }
)
def extract_keywords(text: str, top_k: int = 10) -> List[str]:
    """Extract keywords from provided text."""
    return _plugin.extract_keywords(text, top_k)


# Alternative: Using the new @jarvis_tool decorator
@jarvis_tool(
    name="semantic_summary",
    description="Generate a semantic summary of text",
    tags=["text_analysis", "nlp"]
)
def semantic_summary(text: str, length: str = "short") -> str:
    """
    Generate a semantic summary of text.
    
    Args:
        text: Text to summarize
        length: 'short' (1 sentence), 'medium' (3 sentences), 'long' (5+ sentences)
    """
    length_prompt = {
        "short": "1 sentence",
        "medium": "3 sentences",
        "long": "5-7 sentences"
    }.get(length, "2-3 sentences")
    
    prompt = f"""Summarize this text in {length_prompt}:

{text}

Provide only the summary, no explanations."""
    
    try:
        response = requests.post(
            f"{_plugin.api_url}/api/generate",
            json={
                "model": _plugin.model,
                "prompt": prompt,
                "stream": False
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json().get("response", "")
        else:
            return f"Error: {response.status_code}"
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        return f"Error: {str(e)}"
