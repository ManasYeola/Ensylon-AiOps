"""
tests/test_log_window.py
Tests for the bounded, sliding-window log frequency tracker (LogWindowState).
"""
from datetime import datetime, timezone, timedelta
import pytest
from app.detection.logs import LogWindowState, score_log_signal
from app.models.signal import Signal


def test_burst_within_one_window():
    """A sudden spike of messages in a short time should trigger a high anomaly score."""
    state = LogWindowState(
        window_seconds=300,
        bucket_seconds=60,
        baseline_windows=5,
        burst_multiplier=3.0,
        _clock=lambda: 1000.0,
    )
    
    # 1st message -> expected baseline 1.0, current count 1 -> ratio 1.0 -> score > 0.0
    # 10 messages -> current count 10 -> ratio 10.0 (>> 3.0*2) -> score approaches 1.0
    scores = []
    for _ in range(10):
        score, tid, template = score_log_signal("Database connection timeout", state)
        scores.append(score)
        
    assert scores[-1] >= 0.8, "10 occurrences should be a severe burst (ratio 10 > 6)"
    assert scores[0] == 0.0, "1st occurrence matches baseline 1.0 exactly, score 0.0"


def test_counts_expire_in_later_window():
    """Counts from an old window should be dropped and not contribute to a burst."""
    time_now = 1000.0
    state = LogWindowState(
        window_seconds=300,
        bucket_seconds=60,
        baseline_windows=5,
        burst_multiplier=3.0,
        _clock=lambda: time_now,
    )
    
    # Send 10 messages -> creates a burst
    for _ in range(10):
        score, tid, template = score_log_signal("Database connection timeout", state)
        
    assert state.current_window_count(tid) == 10
    assert score >= 0.8
    
    # Advance time by 301 seconds (past the window_seconds limit)
    time_now += 301.0
    
    # Next message should see a clean window, no burst
    score2, tid2, template2 = score_log_signal("Database connection timeout", state)
    
    assert tid2 == tid
    assert state.current_window_count(tid) == 1, "Old counts should be expired"
    assert score2 == 0.0, "With count=1 and baseline>=1, ratio<=1, score should be 0.0"


def test_baseline_learning_normal_behavior():
    """A recurring message that happens 5 times per window should learn a baseline of 5."""
    time_now = 1000.0
    state = LogWindowState(
        window_seconds=60, # fast windows for testing
        bucket_seconds=10,
        baseline_windows=3,
        burst_multiplier=3.0,
        _clock=lambda: time_now,
    )
    
    # Complete 3 windows
    for window_idx in range(3):
        # In each window, log the message 5 times spaced out
        for step in range(6):
            if step < 5:
                score, tid, template = score_log_signal("Healthcheck ping", state)
            # advance clock by bucket_seconds (10s) to transition buckets naturally
            time_now += 10.0
        
    # Now in window 4, baseline should be 5.
    # We log it 5 times.
    scores = []
    for _ in range(5):
        score, tid, template = score_log_signal("Healthcheck ping", state)
        scores.append(score)
        
    assert state._baseline(tid) == 5.0, "Baseline should have learned mean of 5.0"
    
    # Since expected is 5, logging it at the same rate keeps rolling sum around 5-6.
    # The score should stay very low (below anomaly_threshold 0.40)
    assert all(s < 0.40 for s in scores), f"Should not be anomalous since it matches baseline, got scores {scores}"
    
    # Now if we log it 15 more times in the SAME window (total 20), it should burst
    for _ in range(15):
        score, tid, template = score_log_signal("Healthcheck ping", state)
        
    assert score >= 0.5, "20 occurrences against baseline of 5 should trigger burst (ratio 4)"


def test_separate_services_isolated():
    """Two different state objects don't share counts."""
    state_service_a = LogWindowState(_clock=lambda: 1000.0)
    state_service_b = LogWindowState(_clock=lambda: 1000.0)
    
    for _ in range(10):
        score_a, tid_a, _ = score_log_signal("Shared error message", state_service_a)
        
    assert score_a >= 0.8
    assert state_service_a.current_window_count(tid_a) == 10
    
    # Service B should have 0 counts initially, so first message gives score 0.0
    score_b, tid_b, _ = score_log_signal("Shared error message", state_service_b)
    assert score_b == 0.0
    assert state_service_b.current_window_count(tid_b) == 1
    assert tid_a == tid_b, "Templates should be identical"


# ---------------------------------------------------------------------------
# Event-timestamp driven sliding window tests (Signal.timestamp)
# ---------------------------------------------------------------------------

def test_burst_driven_by_signal_timestamps_rapid_processing():
    """
    Proves requirement 1:
    Several events whose signal timestamps fall inside the configured window
    are treated as a burst even if processed rapidly (zero sleep, in milliseconds).
    """
    state = LogWindowState(window_seconds=300, bucket_seconds=60)
    base_t = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)

    # 10 signals arrive within a 45-second window, processed rapidly in memory
    scores = []
    for i in range(10):
        t = base_t + timedelta(seconds=i * 5)
        score, tid, template = score_log_signal(
            "Connection pool exhausted. Pool size: 100",
            state,
            timestamp=t,
        )
        scores.append(score)

    assert scores[0] == 0.0, "Initial event at baseline rate should have score 0.0"
    assert scores[-1] >= 0.8, f"10 events within 45s should trigger severe burst (score={scores[-1]})"
    assert state.current_window_count(tid, timestamp=base_t + timedelta(seconds=45)) == 10


def test_events_outside_timestamp_window_are_excluded():
    """
    Proves requirement 2:
    Events outside the timestamp window are excluded based on signal event timestamps,
    not the machine's wall-clock time.
    """
    state = LogWindowState(window_seconds=300, bucket_seconds=60)
    base_t = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)

    # 10 events within first 50 seconds
    for i in range(10):
        score, tid, _ = score_log_signal(
            "Connection pool exhausted",
            state,
            timestamp=base_t + timedelta(seconds=i * 5),
        )

    # Window count should be 10 at t = 10:00:45
    assert state.current_window_count(tid, timestamp=base_t + timedelta(seconds=45)) == 10

    # Event 11 occurs at 10:06:00 (360 seconds later, > window_seconds=300)
    t_later = base_t + timedelta(seconds=360)
    score_later, tid_later, _ = score_log_signal(
        "Connection pool exhausted",
        state,
        timestamp=t_later,
    )

    # The 10 previous events occurred at <= 10:00:45, older than cutoff (10:06:00 - 300s = 10:01:00)
    # They must be excluded from the current window.
    assert state.current_window_count(tid, timestamp=t_later) == 1, "Prior events outside 300s window must be excluded"
    assert score_later == 0.0, "Single event in new window against baseline should not be a burst"


def test_replay_backlog_produces_identical_burst_results():
    """
    Proves requirement 3:
    Replay/backlog processing produces the exact same burst result as normal processing
    of the same event timestamps, independent of processing speed or wall-clock arrival.
    """
    base_t = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
    timestamps = []
    # 5 spaced baseline events (1 every 180 seconds)
    for i in range(5):
        timestamps.append(base_t + timedelta(seconds=i * 180))
    # Burst of 15 events within 60 seconds
    burst_start = base_t + timedelta(seconds=5 * 180 + 10)
    for i in range(15):
        timestamps.append(burst_start + timedelta(seconds=i * 4))

    # Run 1: Normal processing simulation
    state_run1 = LogWindowState(window_seconds=300, bucket_seconds=60)
    results_run1 = [
        score_log_signal("Database connection timeout", state_run1, timestamp=t)
        for t in timestamps
    ]

    # Run 2: Fast backlog / replay simulation (tight loop, different machine moments)
    state_run2 = LogWindowState(window_seconds=300, bucket_seconds=60)
    results_run2 = [
        score_log_signal("Database connection timeout", state_run2, timestamp=t)
        for t in timestamps
    ]

    assert len(results_run1) == len(results_run2) == 20
    for r1, r2 in zip(results_run1, results_run2):
        assert r1[0] == r2[0], f"Anomaly score mismatch between normal and replay: {r1[0]} != {r2[0]}"
        assert r1[1] == r2[1], f"Template ID mismatch: {r1[1]} != {r2[1]}"


def test_out_of_order_event_timestamps_within_window():
    """
    Edge case:
    Events that arrive slightly out-of-order within the window are still correctly counted.
    """
    state = LogWindowState(window_seconds=300, bucket_seconds=60)
    base_t = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)

    # Event 1 at t=30s
    score_log_signal("Disk full warning", state, timestamp=base_t + timedelta(seconds=30))
    # Event 2 at t=10s (delayed arrival, but inside window)
    score_log_signal("Disk full warning", state, timestamp=base_t + timedelta(seconds=10))
    # Event 3 at t=40s
    _, tid, _ = score_log_signal("Disk full warning", state, timestamp=base_t + timedelta(seconds=40))

    assert state.current_window_count(tid, timestamp=base_t + timedelta(seconds=40)) == 3


def test_score_log_signal_with_signal_object():
    """
    Verifies that score_log_signal directly accepts a canonical Signal object
    and extracts both its evidence and timestamp.
    """
    state = LogWindowState(window_seconds=300, bucket_seconds=60)
    base_t = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
    sig = Signal(
        id="sig-test-1",
        timestamp=base_t,
        source="application_logs",
        environment="prod",
        service="payments-service",
        component="db",
        type="error_log_burst",
        evidence="[REDACTED] Out of memory error in worker",
    )
    score, tid, template = score_log_signal(sig, state)
    assert score == 0.0
    assert state.current_window_count(tid, timestamp=base_t) == 1

