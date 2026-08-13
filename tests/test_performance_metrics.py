from app.performance_metrics import PerformanceMetrics


def test_window_and_failure_counts_are_kept_separately():
    metrics = PerformanceMetrics(("ct",), window_size=3)

    for elapsed_ms in (10, 20, 30, 40):
        metrics.record("ct", elapsed_ms, success=True)
    metrics.record("ct", 50, success=False)

    ct = metrics.snapshot()["operations"]["ct"]
    assert ct["total_requests"] == 5
    assert ct["total_successes"] == 4
    assert ct["total_failures"] == 1
    assert ct["window_samples"] == 3
    assert ct["avg_ms"] == 30.0
    assert ct["p50_ms"] == 30
    assert ct["p95_ms"] == 40
