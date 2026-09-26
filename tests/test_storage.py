"""
Tests for SQLite storage layer (app/storage/db.py).
"""
from datetime import datetime, timezone
import pytest
from app.models.signal import CanonicalSignal
from app.storage.db import (
    init_db,
    save_signal,
    save_signals_batch,
    get_signal_by_id,
    get_recent_signals,
    get_all_signals,
    get_storage_stats,
)


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_aiops.db"
    init_db(db_file)
    return db_file


def test_save_and_get_signal(temp_db):
    sig = CanonicalSignal(
        timestamp=datetime(2026, 9, 26, 10, 1, 0, tzinfo=timezone.utc),
        source="cloudwatch_metrics",
        environment="prod",
        region="ap-south-1",
        service="payments-service",
        component="db-connection-pool",
        signal_type="metric_anomaly",
        anomaly_score=0.85,
        evidence="[REDACTED_SVC_ACCOUNT] pool exhausted",
        metadata={"threshold": 90, "observed": 98.2},
        value=98.2,
    )

    save_signal(sig, db_path=temp_db)

    fetched = get_signal_by_id(sig.signal_id, db_path=temp_db)
    assert fetched is not None
    assert fetched.signal_id == sig.signal_id
    assert fetched.source == "cloudwatch_metrics"
    assert fetched.service == "payments-service"
    assert fetched.anomaly_score == 0.85
    assert fetched.metadata["threshold"] == 90
    assert fetched.value == 98.2


def test_save_signals_batch_and_stats(temp_db):
    signals = [
        CanonicalSignal(
            timestamp=datetime(2026, 9, 26, 10, 1, i, tzinfo=timezone.utc),
            source="application_logs" if i % 2 == 0 else "grafana_alerts",
            environment="prod",
            region="ap-south-1",
            service=f"service-{i % 3}",
            component="component-1",
            signal_type="error_log_burst",
            anomaly_score=0.1 * i,
            evidence=f"evidence {i}",
        )
        for i in range(10)
    ]

    saved_count = save_signals_batch(signals, db_path=temp_db)
    assert saved_count == 10

    stats = get_storage_stats(db_path=temp_db)
    assert stats["total_signals"] == 10
    assert stats["by_source"]["application_logs"] == 5
    assert stats["by_source"]["grafana_alerts"] == 5
    assert len(stats["top_services"]) == 3


def test_get_recent_signals_window(temp_db):
    now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    old_time = datetime(2026, 9, 26, 11, 50, 0, tzinfo=timezone.utc)  # 10 min ago
    recent_time = datetime(2026, 9, 26, 11, 58, 0, tzinfo=timezone.utc)  # 2 min ago

    old_sig = CanonicalSignal(
        timestamp=old_time,
        source="application_logs",
        environment="prod",
        service="svc-old",
        component="c",
        signal_type="error_log_burst",
    )
    recent_sig = CanonicalSignal(
        timestamp=recent_time,
        source="application_logs",
        environment="prod",
        service="svc-recent",
        component="c",
        signal_type="error_log_burst",
    )

    save_signals_batch([old_sig, recent_sig], db_path=temp_db)

    # 5-minute window relative to `now`
    recent_signals = get_recent_signals(window_minutes=5, reference_time=now, db_path=temp_db)
    assert len(recent_signals) == 1
    assert recent_signals[0].service == "svc-recent"
