"""无需额外依赖的进程内指标收集器。"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: defaultdict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
        self._durations: defaultdict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, **labels: str) -> None:
        key = (name, tuple(sorted((str(k), str(v)) for k, v in labels.items())))
        with self._lock:
            self._counters[key] += 1

    def observe(self, name: str, seconds: float) -> None:
        with self._lock:
            self._durations[name].append(max(0.0, float(seconds)))

    def render_prometheus(self) -> str:
        with self._lock:
            counters = list(self._counters.items())
            durations = {name: list(values) for name, values in self._durations.items()}
        lines = ["# TYPE agent_requests_total counter"]
        for (name, labels), value in sorted(counters):
            label_text = ""
            if labels:
                label_text = "{" + ",".join(f'{k}="{v.replace(chr(34), chr(39))}"' for k, v in labels) + "}"
            lines.append(f"{name}{label_text} {value}")
        for name, values in sorted(durations.items()):
            if values:
                lines.append(f"{name}_seconds_sum {sum(values):.6f}")
                lines.append(f"{name}_seconds_count {len(values)}")
        return "\n".join(lines) + "\n"


class Timer:
    def __init__(self, registry: MetricsRegistry, name: str) -> None:
        self.registry = registry
        self.name = name
        self.started = 0.0

    def __enter__(self):
        self.started = time.monotonic()
        return self

    def __exit__(self, *_exc):
        self.registry.observe(self.name, time.monotonic() - self.started)
