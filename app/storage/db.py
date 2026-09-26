"""
SQLite Storage Layer for Canonical Signals & Incidents.
Provides persistent storage, historical querying, and audit log for AIOps pipeline.
"""
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from app.models.signal import Signal

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "aiops.db"


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Get a configured SQLite database connection.
    Enables WAL mode and foreign keys for high-performance concurrent writes.
    """
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """
    Initialize SQLite schema for canonical signals.
    """
    with get_db_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                signal_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                environment TEXT NOT NULL,
                region TEXT,
                service TEXT NOT NULL,
                component TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                anomaly_score REAL NOT NULL DEFAULT 0.0,
                evidence TEXT,
                metadata TEXT,
                value REAL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals (timestamp);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_signals_service ON signals (service);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_signals_source ON signals (source);"
        )
        conn.commit()


def save_signal(signal: Signal, db_path: Optional[Path] = None) -> None:
    """
    Persist a single CanonicalSignal into the SQLite database.
    """
    init_db(db_path)
    now_utc = datetime.now(timezone.utc).isoformat()
    ts_str = (
        signal.timestamp.isoformat()
        if isinstance(signal.timestamp, datetime)
        else str(signal.timestamp)
    )
    metadata_json = json.dumps(signal.metadata) if signal.metadata else "{}"

    with get_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO signals (
                signal_id, timestamp, source, environment, region,
                service, component, signal_type, anomaly_score,
                evidence, metadata, value, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                signal.signal_id,
                ts_str,
                signal.source,
                signal.environment,
                signal.region,
                signal.service,
                signal.component,
                signal.signal_type,
                signal.anomaly_score,
                signal.evidence,
                metadata_json,
                signal.value,
                now_utc,
            ),
        )
        conn.commit()


def save_signals_batch(signals: List[Signal], db_path: Optional[Path] = None) -> int:
    """
    Batch persist multiple signals in a single atomic transaction.
    """
    if not signals:
        return 0

    init_db(db_path)
    now_utc = datetime.now(timezone.utc).isoformat()
    records = []
    for s in signals:
        ts_str = (
            s.timestamp.isoformat()
            if isinstance(s.timestamp, datetime)
            else str(s.timestamp)
        )
        meta_json = json.dumps(s.metadata) if s.metadata else "{}"
        records.append(
            (
                s.signal_id,
                ts_str,
                s.source,
                s.environment,
                s.region,
                s.service,
                s.component,
                s.signal_type,
                s.anomaly_score,
                s.evidence,
                meta_json,
                s.value,
                now_utc,
            )
        )

    with get_db_connection(db_path) as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO signals (
                signal_id, timestamp, source, environment, region,
                service, component, signal_type, anomaly_score,
                evidence, metadata, value, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            records,
        )
        conn.commit()

    return len(records)


def _row_to_signal(row: sqlite3.Row) -> Signal:
    """
    Convert a SQLite row back to a CanonicalSignal model.
    """
    meta = {}
    if row["metadata"]:
        try:
            meta = json.loads(row["metadata"])
        except Exception:
            meta = {}

    try:
        ts = datetime.fromisoformat(row["timestamp"])
    except Exception:
        ts = datetime.now(timezone.utc)

    return Signal(
        signal_id=row["signal_id"],
        timestamp=ts,
        source=row["source"],
        environment=row["environment"],
        region=row["region"],
        service=row["service"],
        component=row["component"],
        signal_type=row["signal_type"],
        anomaly_score=row["anomaly_score"],
        evidence=row["evidence"],
        metadata=meta,
        value=row["value"],
    )


def get_signal_by_id(signal_id: str, db_path: Optional[Path] = None) -> Optional[Signal]:
    """
    Fetch a signal by its unique signal_id.
    """
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM signals WHERE signal_id = ? LIMIT 1;", (signal_id,)
        )
        row = cursor.fetchone()
        if row:
            return _row_to_signal(row)
    return None


def get_recent_signals(
    window_minutes: int = 5,
    reference_time: Optional[datetime] = None,
    db_path: Optional[Path] = None,
) -> List[Signal]:
    """
    Fetch all signals within a given time window.
    Useful for sliding-window correlation queries.
    """
    init_db(db_path)
    ref = reference_time or datetime.now(timezone.utc)
    # Window start ISO string
    cutoff = datetime.fromtimestamp(
        ref.timestamp() - (window_minutes * 60), tz=timezone.utc
    ).isoformat()

    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM signals WHERE timestamp >= ? ORDER BY timestamp ASC;",
            (cutoff,),
        )
        rows = cursor.fetchall()
        return [_row_to_signal(r) for r in rows]


def get_all_signals(
    limit: int = 500,
    offset: int = 0,
    db_path: Optional[Path] = None,
) -> List[Signal]:
    """
    Fetch all signals with pagination.
    """
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ? OFFSET ?;",
            (limit, offset),
        )
        rows = cursor.fetchall()
        return [_row_to_signal(r) for r in rows]


def get_storage_stats(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Summary metrics on stored canonical signals (useful for demo & presentation).
    """
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM signals;").fetchone()[0]

        source_rows = conn.execute(
            "SELECT source, COUNT(*) as count FROM signals GROUP BY source;"
        ).fetchall()
        by_source = {r["source"]: r["count"] for r in source_rows}

        service_rows = conn.execute(
            "SELECT service, COUNT(*) as count FROM signals GROUP BY service ORDER BY count DESC LIMIT 5;"
        ).fetchall()
        top_services = {r["service"]: r["count"] for r in service_rows}

        return {
            "total_signals": total,
            "by_source": by_source,
            "top_services": top_services,
        }
