"""
Thread-safe in-memory agent status tracker.
Mirrors AgentStatusTracker.cs exactly.
"""

from __future__ import annotations
import threading
from datetime import datetime
from models import AgentActivity, LiveJobStatus


class AgentStatusTracker:
    def __init__(self):
        self._jobs: dict[str, LiveJobStatus] = {}
        self._lock = threading.Lock()

    def update(self, job_id: str, ticker: str, agent: str, step: int, activity: str):
        with self._lock:
            if job_id not in self._jobs:
                self._jobs[job_id] = LiveJobStatus(job_id=job_id)
            key = f"{ticker}::{agent}"
            self._jobs[job_id].active_agents[key] = AgentActivity(
                ticker=ticker, agent=agent, step=step,
                activity=activity, updated_at=datetime.utcnow()
            )
            self._jobs[job_id].last_update = datetime.utcnow()

    def complete(self, job_id: str, ticker: str, agent: str, result: str):
        with self._lock:
            if job_id not in self._jobs:
                return
            key = f"{ticker}::{agent}"
            act = self._jobs[job_id].active_agents.get(key)
            if act:
                act.activity   = f"✅ DONE: {result}"
                act.completed  = True
                act.updated_at = datetime.utcnow()

    def get(self, job_id: str) -> LiveJobStatus | None:
        with self._lock:
            return self._jobs.get(job_id)

    def clear(self, job_id: str):
        with self._lock:
            self._jobs.pop(job_id, None)
