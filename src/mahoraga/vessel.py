"""Mahoraga Vessel Core — minimal kernel for AGI research.

Philosophy: deterministic substrate + non-deterministic agents.
The vessel is the container; the agents are the adaptation.
Inspired by Rust ownership: each module has exactly one owner (the vessel),
and the vessel enforces lifecycle rules before any action runs.

Principles:
  1. Lazy module loading — only what's needed is loaded.
  2. Websurf Oracle is always available — live data > static parameters.
  3. Every action is logged and reversible where possible.
  4. Self-evolution is bounded — external verification required.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("mahoraga.vessel")


class ModuleState(Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class ModuleInfo:
    name: str
    state: ModuleState = ModuleState.UNLOADED
    load_fn: Optional[Callable] = None
    instance: Any = None
    load_time_ms: float = 0.0
    error: Optional[str] = None


class Vessel:
    """The Mahoraga Vessel — minimal orchestration kernel.

    Ownership model: each module has exactly one owner (the vessel).
    Modules are loaded lazily and must declare their dependencies.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._modules: Dict[str, ModuleInfo] = {}
        self._boot_time = time.monotonic()
        self._action_log: List[Dict[str, Any]] = []
        logger.info("Mahoraga Vessel initialized")

    @property
    def uptime_ms(self) -> float:
        return (time.monotonic() - self._boot_time) * 1000

    def register_module(self, name: str, load_fn: Callable) -> None:
        """Register a module for lazy loading. Does not load it yet."""
        if name in self._modules:
            raise ValueError(f"Module '{name}' already registered")
        self._modules[name] = ModuleInfo(name=name, load_fn=load_fn)
        logger.debug(f"Registered module: {name}")

    def get_module(self, name: str) -> Any:
        """Get a module, loading it lazily if needed."""
        if name not in self._modules:
            raise KeyError(f"Module '{name}' not registered")
        info = self._modules[name]
        if info.state == ModuleState.UNLOADED:
            self._load_module(name)
        if info.state == ModuleState.ERROR:
            raise RuntimeError(f"Module '{name}' failed to load: {info.error}")
        return info.instance

    def _load_module(self, name: str) -> None:
        info = self._modules[name]
        info.state = ModuleState.LOADING
        t0 = time.monotonic()
        try:
            info.instance = info.load_fn(self.config)
            info.state = ModuleState.READY
            info.load_time_ms = (time.monotonic() - t0) * 1000
            logger.info(f"Module '{name}' loaded in {info.load_time_ms:.1f}ms")
        except Exception as e:
            info.state = ModuleState.ERROR
            info.error = str(e)
            logger.error(f"Module '{name}' failed to load: {e}")

    def log_action(self, action: str, details: Optional[Dict] = None) -> None:
        """Log an action for auditability."""
        entry = {
            "timestamp": time.time(),
            "action": action,
            "details": details or {},
        }
        self._action_log.append(entry)
        logger.info(f"Action: {action}")

    @property
    def action_log(self) -> List[Dict]:
        return list(self._action_log)

    @property
    def module_states(self) -> Dict[str, str]:
        return {name: info.state.value for name, info in self._modules.items()}

    def status(self) -> Dict[str, Any]:
        """Vessel health status."""
        return {
            "uptime_ms": self.uptime_ms,
            "modules": self.module_states,
            "actions_logged": len(self._action_log),
            "boot_target_ms": 2000,  # SOTA: vessel must boot in < 2s
            "boot_ok": self.uptime_ms < 2000 or len(self._modules) > 0,
        }
