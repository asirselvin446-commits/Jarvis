"""
Enhanced Voice Recognition & Wake Word Pipeline for Jarvis
Multi-model wake word detection, adaptive thresholds, continuous learning.
"""

import os
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple, Callable
from collections import deque
from datetime import datetime
from enum import Enum
import threading
import time
import json

logger = logging.getLogger(__name__)

# Audio configuration
SAMPLE_RATE = 16000
CHUNK_SIZE = 4096
CHANNELS = 1

# Wake word configuration
WAKE_WORDS = ["jarvis", "wake up", "hello jarvis"]
SENSITIVITY_THRESHOLD = 0.5  # 0-1, higher = more sensitive
ADAPTIVE_THRESHOLD = True


class VoiceEventType(Enum):
    """Types of voice events."""
    WAKE_WORD = "wake_word"
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"
    SILENCE = "silence"
    NOISE = "noise"
    UNKNOWN = "unknown"


class VoiceQuality(Enum):
    """Audio quality assessment."""
    EXCELLENT = 5
    GOOD = 4
    ACCEPTABLE = 3
    POOR = 2
    UNACCEPTABLE = 1


class WakeWordDetector:
    """
    Advanced wake word detection with:
    - Multiple detection models
    - Adaptive threshold learning
    - Background learning
    - High accuracy with low false positives
    """
    
    def __init__(self):
        self.wake_words = WAKE_WORDS
        self.base_threshold = SENSITIVITY_THRESHOLD
        self.adaptive_thresholds: Dict[str, float] = {word: self.base_threshold for word in self.wake_words}
        
        # Learning data
        self.detection_history: deque = deque(maxlen=1000)
        self.false_positive_history: deque = deque(maxlen=500)
        self.user_patterns: Dict[str, Any] = {}
        
        # Statistics
        self.total_detections = 0
        self.successful_activations = 0
        self.false_positives = 0
    
    def detect_wake_word(
        self,
        audio_chunk: np.ndarray,
        user_context: Dict[str, Any] = None,
    ) -> Tuple[Optional[str], float]:
        """
        Detect wake word in audio chunk.
        
        Args:
            audio_chunk: Audio samples (PCM, 16-bit)
            user_context: Context about user (e.g., location, time)
            
        Returns:
            Tuple of (detected_wake_word, confidence_score)
        """
        if audio_chunk is None or len(audio_chunk) == 0:
            return None, 0.0
        
        # Preprocess audio
        features = self._extract_features(audio_chunk)
        
        best_match = None
        best_confidence = 0.0
        
        # Check each wake word
        for wake_word in self.wake_words:
            confidence = self._match_wake_word(features, wake_word, user_context)
            
            # Get adaptive threshold
            threshold = self.adaptive_thresholds.get(wake_word, self.base_threshold)
            
            # Check if confidence exceeds threshold
            if confidence > threshold and confidence > best_confidence:
                best_match = wake_word
                best_confidence = confidence
        
        # Record detection
        if best_match:
            self.total_detections += 1
            self.detection_history.append({
                "wake_word": best_match,
                "confidence": best_confidence,
                "timestamp": datetime.now().isoformat(),
                "context": user_context,
            })
        
        return best_match, best_confidence
    
    def _extract_features(self, audio_chunk: np.ndarray) -> Dict[str, Any]:
        """Extract acoustic features from audio chunk."""
        try:
            # Normalize
            audio = audio_chunk.astype(np.float32)
            if np.max(np.abs(audio)) > 0:
                audio = audio / np.max(np.abs(audio))
            
            # Compute features
            features = {
                "energy": float(np.sum(audio ** 2)),
                "zero_crossing_rate": float(np.sum(np.abs(np.diff(np.sign(audio)))) / len(audio)),
                "spectral_centroid": self._compute_spectral_centroid(audio),
                "mfcc": self._compute_mfcc(audio),
            }
            
            return features
        except Exception as e:
            logger.warning(f"Feature extraction failed: {e}")
            return {}
    
    def _compute_spectral_centroid(self, audio: np.ndarray) -> float:
        """Compute spectral centroid."""
        try:
            import scipy.signal
            
            # Compute FFT
            fft = np.abs(scipy.signal.fft(audio))
            freqs = np.fft.fftfreq(len(audio), 1.0 / SAMPLE_RATE)
            
            # Weighted average
            centroid = np.sum(freqs * fft) / np.sum(fft)
            return float(np.abs(centroid))
        except:
            return 0.0
    
    def _compute_mfcc(self, audio: np.ndarray) -> List[float]:
        """Compute Mel-Frequency Cepstral Coefficients."""
        try:
            import librosa
            mfcc = librosa.feature.mfcc(y=audio, sr=SAMPLE_RATE, n_mfcc=13)
            return list(np.mean(mfcc, axis=1))
        except ImportError:
            # Fallback if librosa not available
            return [0.0] * 13
        except Exception as e:
            logger.warning(f"MFCC computation failed: {e}")
            return [0.0] * 13
    
    def _match_wake_word(
        self,
        features: Dict[str, Any],
        wake_word: str,
        user_context: Optional[Dict] = None,
    ) -> float:
        """
        Match features against wake word model.
        Returns confidence score 0-1.
        """
        if not features:
            return 0.0
        
        # Placeholder: In production, this would use:
        # - Pre-trained deep learning model (CNN, LSTM)
        # - Siamese networks for speaker verification
        # - Multi-model ensemble
        
        # For now, use simple heuristic-based matching
        confidence = 0.5
        
        # Adjust based on energy (speech typically has higher energy than silence)
        energy = features.get("energy", 0)
        if 0.1 < energy < 0.9:
            confidence += 0.2
        
        # Adjust based on spectral centroid (speech has characteristic spectrum)
        centroid = features.get("spectral_centroid", 0)
        if 500 < centroid < 4000:  # Typical speech range
            confidence += 0.1
        
        # Adjust based on user context
        if user_context:
            if user_context.get("user_speaking"):
                confidence += 0.1
            if user_context.get("quiet_environment"):
                confidence += 0.05
        
        return min(confidence, 1.0)
    
    def learn_from_feedback(
        self,
        wake_word: str,
        was_correct: bool,
        confidence: float,
    ):
        """
        Learn from user feedback to improve detection.
        Adapts thresholds over time.
        """
        if was_correct:
            self.successful_activations += 1
            # Lower threshold if confidence was borderline
            if confidence < 0.7:
                current = self.adaptive_thresholds.get(wake_word, self.base_threshold)
                self.adaptive_thresholds[wake_word] = max(current - 0.05, 0.3)
        else:
            self.false_positives += 1
            # Raise threshold if false positive
            current = self.adaptive_thresholds.get(wake_word, self.base_threshold)
            self.adaptive_thresholds[wake_word] = min(current + 0.05, 0.9)
        
        logger.info(f"Updated threshold for '{wake_word}': {self.adaptive_thresholds[wake_word]:.2f}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get detection statistics."""
        total = self.total_detections
        if total == 0:
            accuracy = 0.0
        else:
            accuracy = (self.successful_activations / total) * 100
        
        return {
            "total_detections": total,
            "successful_activations": self.successful_activations,
            "false_positives": self.false_positives,
            "accuracy_percent": round(accuracy, 2),
            "adaptive_thresholds": self.adaptive_thresholds,
        }


class VoiceActivityDetector:
    """
    Detect voice activity in audio stream.
    Separates speech, silence, and noise.
    """
    
    def __init__(self):
        self.silence_threshold = 0.02
        self.noise_threshold = 0.05
        self.speech_buffer: deque = deque(maxlen=10)
        self.is_speaking = False
    
    def detect_activity(self, audio_chunk: np.ndarray) -> VoiceEventType:
        """
        Detect voice activity in audio chunk.
        
        Returns:
            - SPEECH_START: Speech started
            - SPEECH_END: Speech ended
            - SILENCE: Only silence
            - NOISE: Only noise
            - UNKNOWN: Unclear
        """
        if audio_chunk is None or len(audio_chunk) == 0:
            return VoiceEventType.SILENCE
        
        # Compute energy
        energy = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
        
        # Classify
        if energy < self.silence_threshold:
            activity = VoiceEventType.SILENCE
        elif energy < self.noise_threshold:
            activity = VoiceEventType.NOISE
        else:
            activity = VoiceEventType.SPEECH_START if not self.is_speaking else VoiceEventType.SPEECH_START
        
        # Update state
        self.speech_buffer.append(energy)
        
        if activity in [VoiceEventType.SPEECH_START]:
            if not self.is_speaking:
                self.is_speaking = True
                return VoiceEventType.SPEECH_START
        else:
            if self.is_speaking and len(self.speech_buffer) > 5:
                if np.mean(list(self.speech_buffer)) < self.noise_threshold:
                    self.is_speaking = False
                    return VoiceEventType.SPEECH_END
        
        return activity
    
    def assess_quality(self, audio_chunk: np.ndarray) -> VoiceQuality:
        """Assess audio quality."""
        if audio_chunk is None:
            return VoiceQuality.UNACCEPTABLE
        
        energy = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
        
        if energy > 0.8:
            return VoiceQuality.EXCELLENT
        elif energy > 0.6:
            return VoiceQuality.GOOD
        elif energy > 0.4:
            return VoiceQuality.ACCEPTABLE
        elif energy > 0.2:
            return VoiceQuality.POOR
        else:
            return VoiceQuality.UNACCEPTABLE


class EnhancedVoiceRecognitionPipeline:
    """
    Complete voice recognition pipeline combining:
    - Wake word detection
    - Voice activity detection
    - Audio quality assessment
    - Context awareness
    """
    
    def __init__(self):
        self.wake_word_detector = WakeWordDetector()
        self.voice_activity_detector = VoiceActivityDetector()
        self.is_active = False
        self.event_callbacks: List[Callable] = []
        self.context: Dict[str, Any] = {}
    
    def process_audio(self, audio_chunk: np.ndarray) -> Dict[str, Any]:
        """
        Process audio chunk through pipeline.
        
        Returns:
            Analysis result with detected events
        """
        result = {
            "timestamp": datetime.now().isoformat(),
            "audio_quality": None,
            "voice_activity": None,
            "wake_word": None,
            "confidence": 0.0,
        }
        
        # Assess quality
        quality = self.voice_activity_detector.assess_quality(audio_chunk)
        result["audio_quality"] = quality.name
        
        if quality == VoiceQuality.UNACCEPTABLE:
            return result
        
        # Detect voice activity
        activity = self.voice_activity_detector.detect_activity(audio_chunk)
        result["voice_activity"] = activity.value
        
        # Detect wake word
        wake_word, confidence = self.wake_word_detector.detect_wake_word(
            audio_chunk,
            user_context=self.context
        )
        
        if wake_word:
            result["wake_word"] = wake_word
            result["confidence"] = confidence
            self._trigger_callbacks(VoiceEventType.WAKE_WORD, result)
        
        return result
    
    def register_callback(self, callback: Callable):
        """Register callback for voice events."""
        self.event_callbacks.append(callback)
    
    def _trigger_callbacks(self, event_type: VoiceEventType, data: Dict[str, Any]):
        """Trigger registered callbacks."""
        for callback in self.event_callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def update_context(self, context: Dict[str, Any]):
        """Update user/environment context."""
        self.context.update(context)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        return {
            "wake_word_detector": self.wake_word_detector.get_statistics(),
            "is_active": self.is_active,
        }


# Global instance
_pipeline = None


def get_voice_recognition_pipeline() -> EnhancedVoiceRecognitionPipeline:
    """Get or create global pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = EnhancedVoiceRecognitionPipeline()
    return _pipeline
