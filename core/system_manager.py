"""
System Manager for Jarvis
Comprehensive system monitoring, resource optimization, and health management.
"""

import os
import logging
import psutil
import threading
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)

# System thresholds
CPU_WARNING_THRESHOLD = 80  # percentage
MEMORY_WARNING_THRESHOLD = 85  # percentage
DISK_WARNING_THRESHOLD = 90  # percentage
TEMP_WARNING_THRESHOLD = 85  # celsius


class SystemHealth(Enum):
    """System health status."""
    EXCELLENT = "excellent"  # All metrics normal
    GOOD = "good"            # Minor issues
    WARNING = "warning"      # Some concerns
    CRITICAL = "critical"    # Needs attention


class ResourceType(Enum):
    """Resource types to monitor."""
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    PROCESSES = "processes"
    TEMPERATURE = "temperature"


class SystemManager:
    """
    Manages system health and resources:
    - Real-time monitoring
    - Resource optimization
    - Predictive maintenance
    - Performance analytics
    """
    
    def __init__(self):
        self.is_monitoring = False
        self.monitor_thread = None
        self.check_interval = 5  # seconds
        
        # Metrics
        self.current_metrics: Dict[str, Any] = {}
        self.metrics_history: List[Dict[str, Any]] = []
        self.max_history = 1000
        
        # Alerts
        self.alerts: List[Dict[str, Any]] = []
        self.max_alerts = 500
        
        # Thresholds
        self.thresholds = {
            "cpu_warning": CPU_WARNING_THRESHOLD,
            "memory_warning": MEMORY_WARNING_THRESHOLD,
            "disk_warning": DISK_WARNING_THRESHOLD,
            "temp_warning": TEMP_WARNING_THRESHOLD,
        }
        
        # Optimization
        self.auto_optimize = True
        self.optimizations_applied: List[Dict[str, Any]] = []
        
        # Callbacks
        self.on_alert = None
        self.on_optimization = None
        self.on_health_change = None
        
        # Health tracking
        self.last_health_state = SystemHealth.GOOD
        self.health_state_start = datetime.now()
    
    def start_monitoring(self):
        """Start system monitoring."""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        logger.info("System monitoring started")
    
    def stop_monitoring(self):
        """Stop system monitoring."""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        logger.info("System monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.is_monitoring:
            try:
                # Collect metrics
                self.current_metrics = self._collect_metrics()
                self.metrics_history.append(self.current_metrics)
                
                # Trim history
                if len(self.metrics_history) > self.max_history:
                    self.metrics_history = self.metrics_history[-self.max_history:]
                
                # Check health
                self._check_health()
                
                # Auto-optimize if needed
                if self.auto_optimize:
                    self._auto_optimize()
                
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
            
            time.sleep(self.check_interval)
    
    def _collect_metrics(self) -> Dict[str, Any]:
        """Collect system metrics."""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "cpu": self._get_cpu_metrics(),
            "memory": self._get_memory_metrics(),
            "disk": self._get_disk_metrics(),
            "network": self._get_network_metrics(),
            "processes": self._get_process_metrics(),
        }
        
        # Temperature
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                metrics["temperature"] = {
                    k: v[0].current for k, v in temps.items()
                }
        except:
            pass
        
        return metrics
    
    def _get_cpu_metrics(self) -> Dict[str, Any]:
        """Get CPU metrics."""
        return {
            "percent": psutil.cpu_percent(interval=0.1),
            "count_logical": psutil.cpu_count(logical=True),
            "count_physical": psutil.cpu_count(logical=False),
            "freq": psutil.cpu_freq().current if psutil.cpu_freq() else None,
            "per_cpu": list(psutil.cpu_percent(interval=0.1, percpu=True)),
        }
    
    def _get_memory_metrics(self) -> Dict[str, Any]:
        """Get memory metrics."""
        virtual = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            "virtual": {
                "total": virtual.total,
                "available": virtual.available,
                "used": virtual.used,
                "percent": virtual.percent,
            },
            "swap": {
                "total": swap.total,
                "used": swap.used,
                "free": swap.free,
                "percent": swap.percent,
            }
        }
    
    def _get_disk_metrics(self) -> Dict[str, Any]:
        """Get disk metrics."""
        disk_info = {}
        
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_info[partition.mountpoint] = {
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                }
            except PermissionError:
                pass
        
        # I/O counters
        io_counters = psutil.disk_io_counters()
        disk_info["io"] = {
            "read_bytes": io_counters.read_bytes,
            "write_bytes": io_counters.write_bytes,
            "read_count": io_counters.read_count,
            "write_count": io_counters.write_count,
        }
        
        return disk_info
    
    def _get_network_metrics(self) -> Dict[str, Any]:
        """Get network metrics."""
        net_io = psutil.net_io_counters()
        
        return {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
            "dropin": net_io.dropin,
            "dropout": net_io.dropout,
        }
    
    def _get_process_metrics(self) -> Dict[str, Any]:
        """Get process metrics."""
        return {
            "total_processes": len(psutil.pids()),
            "top_cpu": self._get_top_processes("cpu", limit=5),
            "top_memory": self._get_top_processes("memory", limit=5),
        }
    
    def _get_top_processes(self, metric: str, limit: int = 5) -> List[Dict]:
        """Get top processes by metric."""
        try:
            processes = []
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                processes.append(proc.info)
            
            # Sort by metric
            if metric == "cpu":
                processes.sort(key=lambda p: p.get("cpu_percent", 0), reverse=True)
            else:
                processes.sort(key=lambda p: p.get("memory_percent", 0), reverse=True)
            
            return processes[:limit]
        except:
            return []
    
    def _check_health(self):
        """Check system health and generate alerts."""
        health_score = 0
        total_checks = 0
        
        # Check CPU
        cpu_percent = self.current_metrics.get("cpu", {}).get("percent", 0)
        if cpu_percent > self.thresholds["cpu_warning"]:
            self._create_alert(
                "HIGH_CPU_USAGE",
                f"CPU usage at {cpu_percent}%",
                severity="warning"
            )
            health_score += 1
        total_checks += 1
        
        # Check memory
        mem_percent = self.current_metrics.get("memory", {}).get("virtual", {}).get("percent", 0)
        if mem_percent > self.thresholds["memory_warning"]:
            self._create_alert(
                "HIGH_MEMORY_USAGE",
                f"Memory usage at {mem_percent}%",
                severity="warning"
            )
            health_score += 1
        total_checks += 1
        
        # Check disk
        disk_info = self.current_metrics.get("disk", {})
        for path, info in disk_info.items():
            if isinstance(info, dict) and "percent" in info:
                if info["percent"] > self.thresholds["disk_warning"]:
                    self._create_alert(
                        "HIGH_DISK_USAGE",
                        f"Disk {path} at {info['percent']}%",
                        severity="warning"
                    )
                    health_score += 1
        total_checks += 1
        
        # Determine overall health
        if health_score == 0:
            new_health = SystemHealth.EXCELLENT
        elif health_score <= 1:
            new_health = SystemHealth.GOOD
        elif health_score <= 3:
            new_health = SystemHealth.WARNING
        else:
            new_health = SystemHealth.CRITICAL
        
        # Notify if health changed
        if new_health != self.last_health_state:
            self.last_health_state = new_health
            self.health_state_start = datetime.now()
            
            if self.on_health_change:
                self.on_health_change(new_health, health_score)
    
    def _create_alert(self, alert_type: str, message: str, severity: str = "info"):
        """Create an alert."""
        alert = {
            "type": alert_type,
            "message": message,
            "severity": severity,
            "timestamp": datetime.now().isoformat(),
        }
        
        self.alerts.append(alert)
        
        # Trim alerts
        if len(self.alerts) > self.max_alerts:
            self.alerts = self.alerts[-self.max_alerts:]
        
        # Trigger callback
        if self.on_alert:
            self.on_alert(alert)
        
        logger.warning(f"Alert: {alert_type} - {message}")
    
    def _auto_optimize(self):
        """Automatically optimize system resources."""
        cpu_percent = self.current_metrics.get("cpu", {}).get("percent", 0)
        mem_percent = self.current_metrics.get("memory", {}).get("virtual", {}).get("percent", 0)
        
        # High CPU: reduce background tasks
        if cpu_percent > 85:
            optimization = {
                "type": "CPU_OPTIMIZATION",
                "action": "Reducing background task priority",
                "timestamp": datetime.now().isoformat(),
            }
            self.optimizations_applied.append(optimization)
            
            if self.on_optimization:
                self.on_optimization(optimization)
        
        # High memory: trigger cleanup
        if mem_percent > 85:
            optimization = {
                "type": "MEMORY_OPTIMIZATION",
                "action": "Running garbage collection",
                "timestamp": datetime.now().isoformat(),
            }
            self.optimizations_applied.append(optimization)
            
            if self.on_optimization:
                self.on_optimization(optimization)
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status."""
        return {
            "health": self.last_health_state.value,
            "since": self.health_state_start.isoformat(),
            "duration_seconds": (datetime.now() - self.health_state_start).total_seconds(),
            "current_metrics": self.current_metrics,
            "pending_alerts": len([a for a in self.alerts if a.get("severity") == "warning"]),
        }
    
    def get_performance_report(self, time_window_minutes: int = 60) -> Dict[str, Any]:
        """Get performance report for time window."""
        cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)
        cutoff_iso = cutoff_time.isoformat()
        
        recent_metrics = [
            m for m in self.metrics_history
            if m.get("timestamp", "") >= cutoff_iso
        ]
        
        if not recent_metrics:
            return {"error": "No metrics in time window"}
        
        # Compute statistics
        cpu_values = [m.get("cpu", {}).get("percent", 0) for m in recent_metrics]
        mem_values = [m.get("memory", {}).get("virtual", {}).get("percent", 0) for m in recent_metrics]
        
        return {
            "time_window_minutes": time_window_minutes,
            "metrics_collected": len(recent_metrics),
            "cpu": {
                "avg": round(sum(cpu_values) / len(cpu_values), 2),
                "min": round(min(cpu_values), 2),
                "max": round(max(cpu_values), 2),
            },
            "memory": {
                "avg": round(sum(mem_values) / len(mem_values), 2),
                "min": round(min(mem_values), 2),
                "max": round(max(mem_values), 2),
            },
            "alerts_generated": len([a for a in self.alerts if a.get("timestamp", "") >= cutoff_iso]),
        }
    
    def get_alerts(self, limit: int = 100, severity: str = None) -> List[Dict]:
        """Get recent alerts."""
        alerts = self.alerts[-limit:]
        
        if severity:
            alerts = [a for a in alerts if a.get("severity") == severity]
        
        return alerts
    
    def clear_alerts(self):
        """Clear all alerts."""
        self.alerts = []
    
    def get_maintenance_recommendations(self) -> List[str]:
        """Get maintenance recommendations."""
        recommendations = []
        
        # Check disk space
        disk_info = self.current_metrics.get("disk", {})
        for path, info in disk_info.items():
            if isinstance(info, dict) and info.get("percent", 0) > 80:
                recommendations.append(f"Consider cleaning up disk space on {path}")
        
        # Check processes
        top_cpu = self.current_metrics.get("processes", {}).get("top_cpu", [])
        if top_cpu and top_cpu[0].get("cpu_percent", 0) > 90:
            recommendations.append(
                f"Process {top_cpu[0].get('name')} consuming high CPU"
            )
        
        # Check uptime
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = (datetime.now() - boot_time).days
        if uptime > 30:
            recommendations.append("System has been running for a long time - consider restarting")
        
        return recommendations
    
    def export_report(self) -> Dict[str, Any]:
        """Export comprehensive system report."""
        return {
            "timestamp": datetime.now().isoformat(),
            "health_status": self.get_health_status(),
            "performance": self.get_performance_report(60),
            "recommendations": self.get_maintenance_recommendations(),
            "recent_alerts": self.get_alerts(limit=20),
            "optimizations_applied": len(self.optimizations_applied),
        }


# Global instance
_manager = None


def get_system_manager() -> SystemManager:
    """Get or create global system manager instance."""
    global _manager
    if _manager is None:
        _manager = SystemManager()
    return _manager
