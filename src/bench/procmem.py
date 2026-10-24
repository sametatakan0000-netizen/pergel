"""Process-tree PSS/CPU sampling from /proc (PSS = shared pages divided among sharers)."""
import os
import threading
from typing import Callable, Dict, List, Optional

CLK_TCK = os.sysconf("SC_CLK_TCK")


def _stat_fields(pid: int) -> Optional[List[str]]:
    """Fields after the ')' of /proc/<pid>/stat: [0]=state [1]=ppid [11]=utime [12]=stime."""
    try:
        with open(f"/proc/{pid}/stat") as fh:
            data = fh.read()
    except OSError:
        return None
    return data[data.rindex(")") + 2:].split()


def _children_map() -> Dict[int, List[int]]:
    kids: Dict[int, List[int]] = {}
    for name in os.listdir("/proc"):
        if name.isdigit():
            f = _stat_fields(int(name))
            if f:
                kids.setdefault(int(f[1]), []).append(int(name))
    return kids


def tree_pids(root: int) -> List[int]:
    kids = _children_map()
    out, stack = [], [root]
    while stack:
        pid = stack.pop()
        out.append(pid)
        stack.extend(kids.get(pid, []))
    return out


def pss_kib(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/smaps_rollup") as fh:
            for line in fh:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


def pids_with_exe_prefix(prefix: str) -> List[int]:
    """Top-level processes whose executable lives under ``prefix`` (parent not also matching)."""
    prefix = os.path.realpath(prefix)
    matched: Dict[int, int] = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            exe = os.path.realpath(os.readlink(f"/proc/{name}/exe"))
        except OSError:
            continue
        f = _stat_fields(int(name))
        if f and exe.startswith(prefix):
            matched[int(name)] = int(f[1])
    return sorted(pid for pid, ppid in matched.items() if ppid not in matched)


class TreeSampler:
    """Samples PSS (peak of the summed tree) and CPU ticks (max per pid, so exited pids still count)."""

    def __init__(self, roots_fn: Callable[[], List[int]], interval_s: float = 0.1) -> None:
        self._roots_fn, self._interval = roots_fn, interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self.peak_pss_kib = 0
        self._ticks: Dict[int, int] = {}

    def _tick(self) -> None:
        pids = set()
        for root in self._roots_fn():
            pids.update(tree_pids(root))
        total = 0
        for pid in pids:
            total += pss_kib(pid)
            f = _stat_fields(pid)
            if f:
                self._ticks[pid] = max(self._ticks.get(pid, 0), int(f[11]) + int(f[12]))
        self.peak_pss_kib = max(self.peak_pss_kib, total)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._tick()
            self._stop.wait(self._interval)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._tick()
        self._stop.set()
        self._thread.join(timeout=2)

    @property
    def cpu_seconds(self) -> float:
        return sum(self._ticks.values()) / CLK_TCK
