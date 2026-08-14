from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from math import ceil
from threading import Lock


class PerformanceMetrics:
    """프로세스 안에서 최근 성공 요청의 지연시간을 집계한다."""

    def __init__(self, operations: tuple[str, ...], window_size: int = 1000):
        if window_size < 1:
            raise ValueError("window_size must be positive")

        self._started_at = datetime.now(timezone.utc).isoformat()
        self._window_size = window_size
        self._lock = Lock()
        self._operations = {
            operation: {
                "latencies": deque(maxlen=window_size),
                "total_requests": 0,
                "total_successes": 0,
                "total_failures": 0,
            }
            for operation in operations
        }

    def record(self, operation: str, elapsed_ms: int, *, success: bool) -> None:
        elapsed_ms = max(0, int(elapsed_ms))
        with self._lock:
            metric = self._operations[operation]
            metric["total_requests"] += 1
            if success:
                metric["total_successes"] += 1
                metric["latencies"].append(elapsed_ms)
            else:
                metric["total_failures"] += 1

    def snapshot(self) -> dict:
        with self._lock:
            operations = {
                name: self._snapshot_operation(metric)
                for name, metric in self._operations.items()
            }

        return {
            "started_at": self._started_at,
            "window_size": self._window_size,
            "operations": operations,
        }

    @staticmethod
    def _snapshot_operation(metric: dict) -> dict:
        values = sorted(metric["latencies"])
        summary = {
            "total_requests": metric["total_requests"],
            "total_successes": metric["total_successes"],
            "total_failures": metric["total_failures"],
            "window_samples": len(values),
            "avg_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "min_ms": None,
            "max_ms": None,
            "last_ms": metric["latencies"][-1] if values else None,
        }
        if not values:
            return summary

        summary.update(
            {
                "avg_ms": round(sum(values) / len(values), 2),
                "p50_ms": PerformanceMetrics._percentile(values, 0.50),
                "p95_ms": PerformanceMetrics._percentile(values, 0.95),
                "min_ms": values[0],
                "max_ms": values[-1],
            }
        )
        return summary

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> int:
        index = max(0, ceil(len(values) * percentile) - 1)
        return values[index]
