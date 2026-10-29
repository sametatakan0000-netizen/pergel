"""Pergel Tab Hibernator - memory saver for inactive tabs.

Discards/hibernates background tabs to reduce RAM usage.
SOTA reference: Edge Sleeping Tabs, Brave Memory Saver, Chrome Memory Saver.
"""
import time


class TabHibernator:
    """Manages tab hibernation to reduce memory usage."""

    DEFAULT_IDLE_TIMEOUT = 300  # 5 minutes

    def __init__(self, idle_timeout: int = DEFAULT_IDLE_TIMEOUT):
        self.idle_timeout = idle_timeout
        self.tab_activity: dict = {}
        self.hibernated_tabs: set = set()

    def track_activity(self, tab_id: str) -> None:
        self.tab_activity[tab_id] = time.time()
        self.hibernated_tabs.discard(tab_id)

    def get_idle_tabs(self) -> list:
        now = time.time()
        return [
            tid for tid, ts in self.tab_activity.items()
            if now - ts > self.idle_timeout and tid not in self.hibernated_tabs
        ]

    def should_hibernate(self, tab_id: str) -> bool:
        if tab_id in self.hibernated_tabs:
            return False
        last = self.tab_activity.get(tab_id)
        return last is not None and (time.time() - last) > self.idle_timeout

    def mark_hibernated(self, tab_id: str) -> None:
        self.hibernated_tabs.add(tab_id)

    def mark_active(self, tab_id: str) -> None:
        self.hibernated_tabs.discard(tab_id)
        self.tab_activity[tab_id] = time.time()

    def get_memory_stats(self) -> dict:
        return {
            "total_tracked": len(self.tab_activity),
            "hibernated": len(self.hibernated_tabs),
            "idle_candidates": len(self.get_idle_tabs()),
            "idle_timeout_seconds": self.idle_timeout,
        }
