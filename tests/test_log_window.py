"""
tests/test_log_window.py
Tests for the bounded, sliding-window log frequency tracker (LogWindowState).
"""
import pytest
from app.detection.logs import LogWindowState, score_log_signal


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
