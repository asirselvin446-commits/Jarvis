"""
Advanced Task Orchestrator for Jarvis
Handles complex multi-step workflows with dependencies, parallelization, and error recovery.
"""

import uuid
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Set
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict, deque
import json

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task execution state."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class TaskPriority(Enum):
    """Task execution priority."""
    CRITICAL = 5
    HIGH = 4
    NORMAL = 3
    LOW = 2
    DEFERRED = 1


@dataclass
class TaskResult:
    """Result of a task execution."""
    task_id: str
    status: TaskStatus
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": str(self.output)[:500],  # Truncate for JSON
            "error": self.error,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
        }


@dataclass
class Task:
    """A single task in the workflow."""
    id: str
    name: str
    agent_name: str  # Which agent should execute this
    params: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    priority: TaskPriority = TaskPriority.NORMAL
    timeout_seconds: int = 300
    retry_on_fail: int = 1
    fallback_tasks: List[str] = field(default_factory=list)
    parallel_ok: bool = True
    required: bool = True  # If False, failure doesn't block workflow
    
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[TaskResult] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "agent_name": self.agent_name,
            "params": self.params,
            "dependencies": self.dependencies,
            "priority": self.priority.name,
            "status": self.status.value,
            "result": self.result.to_dict() if self.result else None,
        }


class AdvancedOrchestrator:
    """
    Advanced workflow orchestrator supporting:
    - Task DAG with dependency resolution
    - Parallel execution of independent tasks
    - Error handling and automatic recovery
    - State tracking and history
    """
    
    def __init__(self, max_concurrent: int = 5):
        self.tasks: Dict[str, Task] = {}
        self.execution_order: List[str] = []
        self.max_concurrent = max_concurrent
        self.execution_history: List[TaskResult] = []
        self.current_workflow_id = None
        self._build_graph_cache = {}
    
    def add_task(
        self,
        name: str,
        agent_name: str,
        params: Dict[str, Any],
        dependencies: List[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout_seconds: int = 300,
        retry_on_fail: int = 1,
        fallback_tasks: List[str] = None,
        task_id: str = None,
    ) -> Task:
        """Add a task to the workflow."""
        task_id = task_id or str(uuid.uuid4())[:8]
        
        task = Task(
            id=task_id,
            name=name,
            agent_name=agent_name,
            params=params,
            dependencies=dependencies or [],
            priority=priority,
            timeout_seconds=timeout_seconds,
            retry_on_fail=retry_on_fail,
            fallback_tasks=fallback_tasks or [],
        )
        
        self.tasks[task_id] = task
        self._build_graph_cache.clear()  # Invalidate cache
        
        logger.info(f"Added task: {name} ({task_id})")
        return task
    
    def build_execution_plan(self) -> List[List[str]]:
        """
        Build execution plan respecting dependencies.
        Returns list of task batches that can execute in parallel.
        """
        # Check for circular dependencies
        if self._has_circular_dependency():
            raise ValueError("Circular dependency detected in task graph")
        
        # Topological sort with levels
        batches = []
        completed = set()
        in_progress = set()
        
        while len(completed) < len(self.tasks):
            # Find ready tasks (all dependencies completed)
            ready = []
            for task_id, task in self.tasks.items():
                if task_id not in completed and task_id not in in_progress:
                    if all(dep in completed for dep in task.dependencies):
                        ready.append(task_id)
            
            if not ready and (completed | in_progress) < set(self.tasks.keys()):
                raise ValueError("Cannot resolve task dependencies - possible circular dependency")
            
            # Sort ready tasks by priority
            ready.sort(key=lambda tid: self.tasks[tid].priority.value, reverse=True)
            
            # Group into batch (respecting max_concurrent)
            batch = []
            for task_id in ready:
                if len(batch) < self.max_concurrent:
                    batch.append(task_id)
                    in_progress.add(task_id)
            
            if batch:
                batches.append(batch)
            
            # Mark batch as completed for next iteration
            for task_id in batch:
                completed.add(task_id)
                in_progress.remove(task_id)
        
        logger.info(f"Built execution plan: {len(batches)} batches")
        return batches
    
    def _has_circular_dependency(self) -> bool:
        """Detect circular dependencies using DFS."""
        visited = set()
        rec_stack = set()
        
        def has_cycle(node):
            visited.add(node)
            rec_stack.add(node)
            
            task = self.tasks.get(node)
            if task:
                for dep in task.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True
            
            rec_stack.remove(node)
            return False
        
        for task_id in self.tasks:
            if task_id not in visited:
                if has_cycle(task_id):
                    return True
        
        return False
    
    def get_task_dependencies(self, task_id: str) -> Dict[str, TaskResult]:
        """Get results from all dependencies of a task."""
        task = self.tasks.get(task_id)
        if not task:
            return {}
        
        deps = {}
        for dep_id in task.dependencies:
            dep_task = self.tasks.get(dep_id)
            if dep_task and dep_task.result:
                deps[dep_id] = dep_task.result
        
        return deps
    
    def execute_task(
        self,
        task_id: str,
        executor_func: Callable[[Task, Dict[str, TaskResult]], TaskResult],
    ) -> TaskResult:
        """
        Execute a single task with the provided executor.
        
        Args:
            task_id: ID of task to execute
            executor_func: Function that executes the task
                          Signature: (task, dependency_results) -> TaskResult
        """
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        task.status = TaskStatus.RUNNING
        start_time = datetime.now()
        
        try:
            # Get dependency results
            dep_results = self.get_task_dependencies(task_id)
            
            # Execute task
            result = executor_func(task, dep_results)
            result.task_id = task_id
            
            # Update task
            task.status = result.status
            task.result = result
            
            # Log to history
            self.execution_history.append(result)
            
            logger.info(f"✓ Task completed: {task.name} ({task_id}) - {result.status.value}")
            return result
            
        except Exception as e:
            logger.error(f"Task failed: {task_id} - {str(e)}")
            
            result = TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
            )
            
            task.status = TaskStatus.FAILED
            task.result = result
            self.execution_history.append(result)
            
            return result
    
    def handle_task_failure(
        self,
        task_id: str,
        retry: bool = True,
    ) -> Optional[str]:
        """
        Handle task failure with retry or fallback.
        
        Returns:
            - None if handled and should retry
            - fallback_task_id if falling back
            - raises exception if unrecoverable
        """
        task = self.tasks.get(task_id)
        if not task:
            return None
        
        # Try retry first
        if retry and task.result and task.result.retry_count < task.retry_on_fail:
            task.result.retry_count += 1
            task.status = TaskStatus.RETRY
            logger.info(f"Retrying task: {task_id} (attempt {task.result.retry_count})")
            return None
        
        # Try fallback
        if task.fallback_tasks:
            fallback_id = task.fallback_tasks[0]
            logger.info(f"Falling back to: {fallback_id}")
            return fallback_id
        
        # If required, raise error
        if task.required:
            raise RuntimeError(f"Critical task failed: {task_id}")
        
        # If optional, skip
        task.status = TaskStatus.SKIPPED
        logger.warning(f"Optional task skipped: {task_id}")
        return None
    
    def get_workflow_status(self) -> Dict[str, Any]:
        """Get current workflow status."""
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks.values() if t.status in [TaskStatus.SUCCESS, TaskStatus.SKIPPED])
        failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
        running = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)
        
        return {
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": total - completed - failed - running,
            "success_rate": round((completed / total * 100), 2) if total > 0 else 0,
            "execution_history_size": len(self.execution_history),
        }
    
    def get_failed_tasks(self) -> List[Task]:
        """Get all failed tasks."""
        return [t for t in self.tasks.values() if t.status == TaskStatus.FAILED]
    
    def get_ready_tasks(self) -> List[Task]:
        """Get all tasks ready to execute."""
        completed = {t.id for t in self.tasks.values() if t.status == TaskStatus.SUCCESS}
        return [
            t for t in self.tasks.values()
            if t.status == TaskStatus.PENDING
            and all(dep in completed for dep in t.dependencies)
        ]
    
    def clear_workflow(self):
        """Clear current workflow."""
        self.tasks.clear()
        self.execution_order.clear()
        self.execution_history.clear()
        self._build_graph_cache.clear()
        logger.info("Workflow cleared")
    
    def export_workflow(self) -> Dict[str, Any]:
        """Export current workflow as JSON."""
        return {
            "workflow_id": self.current_workflow_id,
            "created_at": datetime.now().isoformat(),
            "tasks": {tid: t.to_dict() for tid, t in self.tasks.items()},
            "execution_plan": self.build_execution_plan(),
            "status": self.get_workflow_status(),
        }
    
    def import_workflow(self, workflow_dict: Dict[str, Any]):
        """Import workflow from JSON."""
        self.clear_workflow()
        # TODO: Implement workflow import
        logger.info("Workflow imported")


# Global orchestrator instance
_orchestrator = None


def get_orchestrator() -> AdvancedOrchestrator:
    """Get or create global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AdvancedOrchestrator()
    return _orchestrator
