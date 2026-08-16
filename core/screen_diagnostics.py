"""
Screen Diagnostics & Issue Detection System for Jarvis
Real-time monitoring, issue detection, and auto-remediation suggestions.
"""

import os
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

import pyautogui
from PIL import Image
import requests

logger = logging.getLogger(__name__)

# Vision model configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
VISION_MODEL = "qwen2.5vl:3b"


class IssueType(Enum):
    """Types of issues that can be detected."""
    ERROR_DIALOG = "error_dialog"
    WARNING_DIALOG = "warning_dialog"
    FROZEN_APP = "frozen_app"
    HIGH_CPU = "high_cpu"
    HIGH_MEMORY = "high_memory"
    DISK_FULL = "disk_full"
    NETWORK_ISSUE = "network_issue"
    PERMISSION_ERROR = "permission_error"
    FILE_NOT_FOUND = "file_not_found"
    TIMEOUT = "timeout"
    CONNECTIVITY = "connectivity"
    PERFORMANCE = "performance"
    SECURITY = "security"
    UNKNOWN = "unknown"


class IssueSeverity(Enum):
    """Issue severity levels."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    INFO = 5


@dataclass
class Issue:
    """Represents a detected system or application issue."""
    id: str
    issue_type: IssueType
    severity: IssueSeverity
    title: str
    description: str
    affected_app: Optional[str] = None
    screen_region: Optional[Tuple[int, int, int, int]] = None  # x, y, width, height
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved_at: Optional[str] = None
    remediation_steps: List[str] = field(default_factory=list)
    auto_fix_available: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.issue_type.value,
            "severity": self.severity.name,
            "title": self.title,
            "description": self.description,
            "affected_app": self.affected_app,
            "detected_at": self.detected_at,
            "remediation_steps": self.remediation_steps,
            "auto_fix_available": self.auto_fix_available,
        }


class ScreenDiagnostics:
    """
    Monitor screen for issues and provide diagnostics.
    Combines visual analysis with system metrics.
    """
    
    def __init__(self, check_interval_seconds: int = 5):
        self.check_interval = check_interval_seconds
        self.monitoring = False
        self.monitor_thread = None
        
        self.detected_issues: Dict[str, Issue] = {}
        self.issue_history: List[Issue] = []
        self.last_screen_state = None
        self.last_check_time = None
        
        self.max_history = 100
        self.issue_callbacks: List[callable] = []
    
    def start_monitoring(self):
        """Start background screen monitoring."""
        if self.monitoring:
            logger.warning("Monitoring already running")
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True
        )
        self.monitor_thread.start()
        logger.info("Screen monitoring started")
    
    def stop_monitoring(self):
        """Stop background monitoring."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Screen monitoring stopped")
    
    def _monitor_loop(self):
        """Background monitoring loop."""
        while self.monitoring:
            try:
                self.check_for_issues()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
    
    def check_for_issues(self) -> List[Issue]:
        """
        Perform comprehensive issue detection.
        Combines screen analysis with system metrics.
        """
        new_issues = []
        
        # Check visual issues (errors, warnings, UI problems)
        visual_issues = self._check_visual_issues()
        new_issues.extend(visual_issues)
        
        # Check system metrics
        system_issues = self._check_system_health()
        new_issues.extend(system_issues)
        
        # Check application-specific issues
        app_issues = self._check_application_health()
        new_issues.extend(app_issues)
        
        # Update tracking
        for issue in new_issues:
            if issue.id not in self.detected_issues:
                self.detected_issues[issue.id] = issue
                self._notify_issue_detected(issue)
        
        self.last_check_time = datetime.now()
        return new_issues
    
    def _check_visual_issues(self) -> List[Issue]:
        """Detect visual issues on screen (errors, warnings)."""
        issues = []
        
        try:
            # Capture screen
            screenshot = pyautogui.screenshot()
            
            # Analyze with vision model
            analysis = self._analyze_screen_vision(screenshot)
            
            if analysis.get("error_detected"):
                issue = Issue(
                    id=f"visual_error_{datetime.now().timestamp()}",
                    issue_type=IssueType.ERROR_DIALOG,
                    severity=IssueSeverity.HIGH,
                    title="Error Dialog Detected",
                    description=analysis.get("error_message", "Unknown error"),
                    remediation_steps=analysis.get("suggested_fixes", []),
                    auto_fix_available=len(analysis.get("suggested_fixes", [])) > 0,
                )
                issues.append(issue)
            
            if analysis.get("warning_detected"):
                issue = Issue(
                    id=f"visual_warning_{datetime.now().timestamp()}",
                    issue_type=IssueType.WARNING_DIALOG,
                    severity=IssueSeverity.MEDIUM,
                    title="Warning Dialog Detected",
                    description=analysis.get("warning_message", "Unknown warning"),
                )
                issues.append(issue)
            
            self.last_screen_state = screenshot
            
        except Exception as e:
            logger.warning(f"Visual analysis failed: {e}")
        
        return issues
    
    def _check_system_health(self) -> List[Issue]:
        """Detect system-level issues."""
        issues = []
        
        try:
            import psutil
            
            # Check CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            if cpu_percent > 90:
                issue = Issue(
                    id=f"high_cpu_{datetime.now().timestamp()}",
                    issue_type=IssueType.HIGH_CPU,
                    severity=IssueSeverity.HIGH if cpu_percent > 95 else IssueSeverity.MEDIUM,
                    title=f"High CPU Usage: {cpu_percent}%",
                    description=f"CPU usage is at {cpu_percent}%. System may be slow.",
                    remediation_steps=[
                        "Check Task Manager for resource-heavy processes",
                        "Close unnecessary applications",
                        "Restart resource-heavy services",
                    ],
                    metadata={"cpu_percent": cpu_percent}
                )
                issues.append(issue)
            
            # Check Memory
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                issue = Issue(
                    id=f"high_memory_{datetime.now().timestamp()}",
                    issue_type=IssueType.HIGH_MEMORY,
                    severity=IssueSeverity.HIGH if memory.percent > 95 else IssueSeverity.MEDIUM,
                    title=f"High Memory Usage: {memory.percent}%",
                    description=f"Memory usage is at {memory.percent}%. Available: {memory.available / (1024**3):.2f}GB",
                    remediation_steps=[
                        "Close unused applications",
                        "Clear browser cache",
                        "Restart system if necessary",
                    ],
                    metadata={"memory_percent": memory.percent}
                )
                issues.append(issue)
            
            # Check Disk Space
            disk = psutil.disk_usage('/')
            if disk.percent > 90:
                issue = Issue(
                    id=f"disk_full_{datetime.now().timestamp()}",
                    issue_type=IssueType.DISK_FULL,
                    severity=IssueSeverity.CRITICAL if disk.percent > 95 else IssueSeverity.HIGH,
                    title=f"Low Disk Space: {disk.percent}%",
                    description=f"Disk space is {disk.percent}% full. {disk.free / (1024**3):.2f}GB remaining.",
                    remediation_steps=[
                        "Delete temporary files",
                        "Run disk cleanup",
                        "Uninstall unused programs",
                        "Move large files to external storage",
                    ],
                    auto_fix_available=True,
                    metadata={"disk_percent": disk.percent}
                )
                issues.append(issue)
            
        except ImportError:
            logger.warning("psutil not available for system health checks")
        except Exception as e:
            logger.error(f"System health check failed: {e}")
        
        return issues
    
    def _check_application_health(self) -> List[Issue]:
        """Detect application-specific issues."""
        issues = []
        
        try:
            # Get active window
            active_window = self._get_active_window()
            if not active_window:
                return issues
            
            # Check if application is responding
            if self._is_app_frozen(active_window):
                issue = Issue(
                    id=f"frozen_app_{datetime.now().timestamp()}",
                    issue_type=IssueType.FROZEN_APP,
                    severity=IssueSeverity.CRITICAL,
                    title=f"Application Not Responding: {active_window}",
                    description=f"{active_window} is not responding to input.",
                    affected_app=active_window,
                    remediation_steps=[
                        "Wait a moment for the application to respond",
                        "Try closing the application window",
                        "Use Task Manager to force close",
                        "Restart the application",
                    ],
                    auto_fix_available=True,
                )
                issues.append(issue)
        
        except Exception as e:
            logger.debug(f"Application health check failed: {e}")
        
        return issues
    
    def _analyze_screen_vision(self, screenshot: Image) -> Dict[str, Any]:
        """Analyze screen using vision model."""
        try:
            import base64
            from io import BytesIO
            
            # Convert to base64
            buffered = BytesIO()
            screenshot.save(buffered, format="JPEG", quality=85)
            b64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            # Analyze with vision model
            prompt = """Analyze this screen for:
1. Any error dialogs or messages
2. Any warning dialogs
3. System issues or alerts

Respond in JSON format with keys:
- error_detected (bool)
- error_message (str)
- warning_detected (bool)
- warning_message (str)
- suggested_fixes (list)
"""
            
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": VISION_MODEL,
                    "prompt": prompt,
                    "images": [b64_image],
                    "stream": False,
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result_text = response.json().get("response", "")
                # Parse JSON from response
                import json as json_lib
                try:
                    analysis = json_lib.loads(result_text)
                    return analysis
                except:
                    return {
                        "error_detected": False,
                        "warning_detected": False,
                        "suggested_fixes": []
                    }
            
        except Exception as e:
            logger.debug(f"Vision analysis failed: {e}")
        
        return {
            "error_detected": False,
            "warning_detected": False,
            "suggested_fixes": []
        }
    
    def _get_active_window(self) -> Optional[str]:
        """Get name of active window."""
        try:
            import pygetwindow
            active = pygetwindow.getActiveWindow()
            return active.title if active else None
        except:
            return None
    
    def _is_app_frozen(self, app_name: str) -> bool:
        """Check if application is frozen/not responding."""
        try:
            import pygetwindow
            windows = pygetwindow.getWindowsWithTitle(app_name)
            for window in windows:
                if not window.isActive:
                    return True
        except:
            pass
        return False
    
    def _notify_issue_detected(self, issue: Issue):
        """Notify callbacks of detected issue."""
        self.issue_history.append(issue)
        if len(self.issue_history) > self.max_history:
            self.issue_history.pop(0)
        
        for callback in self.issue_callbacks:
            try:
                callback(issue)
            except Exception as e:
                logger.error(f"Issue callback error: {e}")
    
    def register_issue_callback(self, callback: callable):
        """Register a callback for detected issues."""
        self.issue_callbacks.append(callback)
    
    def get_active_issues(self) -> List[Issue]:
        """Get all currently active issues."""
        return list(self.detected_issues.values())
    
    def get_critical_issues(self) -> List[Issue]:
        """Get all critical-severity issues."""
        return [
            i for i in self.detected_issues.values()
            if i.severity == IssueSeverity.CRITICAL
        ]
    
    def resolve_issue(self, issue_id: str):
        """Mark an issue as resolved."""
        if issue_id in self.detected_issues:
            self.detected_issues[issue_id].resolved_at = datetime.now().isoformat()
            del self.detected_issues[issue_id]
            logger.info(f"Issue resolved: {issue_id}")
    
    def get_diagnostics_report(self) -> Dict[str, Any]:
        """Get comprehensive diagnostics report."""
        return {
            "timestamp": datetime.now().isoformat(),
            "active_issues": len(self.detected_issues),
            "critical_issues": len(self.get_critical_issues()),
            "issues": [i.to_dict() for i in self.get_active_issues()],
            "issue_history_size": len(self.issue_history),
            "monitoring_active": self.monitoring,
        }


# Global instance
_diagnostics = None


def get_screen_diagnostics() -> ScreenDiagnostics:
    """Get or create global diagnostics instance."""
    global _diagnostics
    if _diagnostics is None:
        _diagnostics = ScreenDiagnostics()
    return _diagnostics
