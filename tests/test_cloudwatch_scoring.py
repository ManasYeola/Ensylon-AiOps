"""
tests/test_cloudwatch_scoring.py

Focused tests for CloudWatch payload → normalization → detection scoring.

Scenarios from problem-statement.html:
  - ALARM event (DB connection pool at 91.3 vs threshold 90) — must be anomalous
  - OK / recovery event — must score 0.0 and not enter the pipeline
  - Missing metric values (no ObservedValue, no Threshold) — graceful degradation
  - First event with no history — ALARM state must still produce meaningful score
  - Score components are explicit (breach ratio, z-score, EWMA)
"""
import pytest
from datetime import datetime, timezone

from app.ingestion.cloudwatch import normalize_cloudwatch
from app.detection.metrics import score_metric_signal, _breach_ratio


# ---------------------------------------------------------------------------
# Reference payload from problem-statement.html (DB connection-pool example)
# ---------------------------------------------------------------------------

_PS_ALARM_PAYLOAD = {
    "AlarmName": "HighDBConnections-payments-service",
    "AlarmDescription": "DB connection pool utilisation exceeded 90% threshold",
    "StateChangeTime": "2026-09-26T10:01:00Z",
    "Region": "ap-south-1",
    "NewStateValue": "ALARM",
    "OldStateValue": "OK",
    "Trigger": {
        "MetricName": "DBConnectionCount",
        "Namespace": "AWS/RDS",
        "Threshold": 90,
        "ObservedValue": 91.3,
        "Statistic": "AVERAGE",
        "Period": 60,
        "EvaluationPeriods": 3,
    },
    "AffectedResources": {
        "service": "agency-db",
        "component": "db-connection-pool",
        "environment": "prod",
        "region": "ap-south-1",
        "accountId": "456789012345",
        "serviceAccount": "svc-payments@internal.corp.com",
    },
}

_PS_OK_PAYLOAD = {
    **_PS_ALARM_PAYLOAD,
    "NewStateValue": "OK",
    "OldStateValue": "ALARM",
    "Trigger": {
        **_PS_ALARM_PAYLOAD["Trigger"],
        "ObservedValue": 45.0,   # recovered — well below threshold
    },
}


# ===========================================================================
# 1. Normalizer produces correct metadata keys
# ===========================================================================

class TestCloudWatchNormalization:
    def test_alarm_payload_has_alarm_state_in_metadata(self):
        sig = normalize_cloudwatch(_PS_ALARM_PAYLOAD)
        assert sig.metadata["alarm_state"] == "ALARM"
        assert sig.metadata["new_state"] == "ALARM"
        assert sig.metadata["old_state"] == "OK"

    def test_alarm_payload_observed_and_threshold_stored_flat(self):
        sig = normalize_cloudwatch(_PS_ALARM_PAYLOAD)
        assert sig.metadata["observed_value"] == 91.3
        assert sig.metadata["threshold_value"] == 90.0

    def test_alarm_payload_value_is_observed_value(self):
        """signal.value must be ObservedValue so the z-score scorer gets the right number."""
        sig = normalize_cloudwatch(_PS_ALARM_PAYLOAD)
        assert sig.value == 91.3

    def test_ok_payload_alarm_state_is_ok(self):
        sig = normalize_cloudwatch(_PS_OK_PAYLOAD)
        assert sig.metadata["alarm_state"] == "OK"

    def test_ok_payload_evidence_says_recovered(self):
        sig = normalize_cloudwatch(_PS_OK_PAYLOAD)
        assert "recover" in sig.evidence.lower()

    def test_alarm_payload_evidence_contains_alarm(self):
        sig = normalize_cloudwatch(_PS_ALARM_PAYLOAD)
        # When AlarmDescription is present it becomes the evidence
        assert "DB connection pool" in sig.evidence

    def test_alarm_payload_service_and_component(self):
        sig = normalize_cloudwatch(_PS_ALARM_PAYLOAD)
        assert sig.service == "agency-db"
        assert sig.component == "db-connection-pool"

    def test_pii_redacted_from_affected_resources(self):
        sig = normalize_cloudwatch(_PS_ALARM_PAYLOAD)
        assert "svc-payments@internal.corp.com" not in str(sig.metadata)
        assert "[REDACTED_SVC_ACCOUNT]" in str(sig.metadata)
        assert "456789012345" not in str(sig.metadata)


# ===========================================================================
# 2. _breach_ratio helper
# ===========================================================================

class TestBreachRatio:
    def test_no_breach_when_at_threshold(self):
        assert _breach_ratio(90.0, 90.0) == 0.0

    def test_no_breach_when_below_threshold(self):
        assert _breach_ratio(45.0, 90.0) == 0.0

    def test_small_breach(self):
        ratio = _breach_ratio(91.3, 90.0)
        assert abs(ratio - (91.3 - 90.0) / 90.0) < 1e-9

    def test_double_threshold(self):
        ratio = _breach_ratio(180.0, 90.0)
        assert abs(ratio - 1.0) < 1e-9

    def test_zero_threshold_returns_zero(self):
        assert _breach_ratio(100.0, 0.0) == 0.0


# ===========================================================================
# 3. score_metric_signal — OK state always returns 0.0
# ===========================================================================

class TestOKStateScoring:
    def test_ok_state_with_no_history_returns_zero(self):
        score = score_metric_signal(
            history=[],
            current_value=45.0,
            threshold_value=90.0,
            alarm_state="OK",
        )
        assert score == 0.0

    def test_ok_state_with_long_history_returns_zero(self):
        """Even if history makes the value look like an outlier, OK → 0.0."""
        history = [90.0] * 20   # baseline of 90; 45 would be a big negative deviation
        score = score_metric_signal(
            history=history,
            current_value=45.0,
            threshold_value=90.0,
            alarm_state="OK",
        )
        assert score == 0.0

    def test_ok_state_case_insensitive(self):
        score = score_metric_signal(
            history=[],
            current_value=45.0,
            alarm_state="ok",
        )
        assert score == 0.0


# ===========================================================================
# 4. score_metric_signal — ALARM state, no history (first event)
# ===========================================================================

class TestAlarmWithNoHistory:
    """
    The PS scenario: DB connection pool first exceeds threshold.
    There are no prior readings in history.  The ALARM state alone with
    threshold breach must produce a meaningful anomaly_score ≥ 0.55.
    """
    def test_alarm_no_history_above_threshold_scores_above_floor(self):
        score = score_metric_signal(
            history=[],
            current_value=91.3,
            threshold_value=90.0,
            alarm_state="ALARM",
        )
        # Floor is 0.55 for any confirmed ALARM breach
        assert score >= 0.55, (
            f"Expected ≥ 0.55 for confirmed ALARM with no history, got {score}"
        )

    def test_alarm_no_history_score_is_float_in_range(self):
        score = score_metric_signal(
            history=[],
            current_value=91.3,
            threshold_value=90.0,
            alarm_state="ALARM",
        )
        assert 0.0 <= score <= 1.0

    def test_alarm_large_breach_scores_higher_than_small_breach(self):
        # With history the z-score component differentiates:
        # 180 vs baseline-of-90s produces a large z-score;
        # 91.3 vs baseline-of-90s is nearly zero z-score → both get floor
        # but large breach also gets a higher breach_score → higher total.
        history = [90.0] * 10
        score_small = score_metric_signal(
            history=history, current_value=91.3, threshold_value=90.0, alarm_state="ALARM"
        )
        score_large = score_metric_signal(
            history=history, current_value=180.0, threshold_value=90.0, alarm_state="ALARM"
        )
        assert score_large > score_small, (
            f"Larger breach ({score_large}) must produce higher score than small breach ({score_small})"
        )

    def test_alarm_large_breach_approaches_max(self):
        # 2× threshold, no history:
        #   breach_score = min(_breach_ratio(180, 90), 1.0) = 1.0
        #   blended = 0.55*1.0 + 0.30*0 + 0.15*0 = 0.55
        #   floor(ALARM, 180 > 90): max(0.55, 0.55) = 0.55
        # With history the z-score component adds more.
        score = score_metric_signal(
            history=[],
            current_value=180.0,   # 2× threshold
            threshold_value=90.0,
            alarm_state="ALARM",
        )
        assert score >= 0.55


# ===========================================================================
# 5. score_metric_signal — ALARM state, with history
# ===========================================================================

class TestAlarmWithHistory:
    """Z-score and EWMA contribute when history is present."""

    def test_alarm_with_stable_history_still_anomalous(self):
        """History of 90s; current is 91.3 — statistically unremarkable but ALARM confirmed."""
        history = [90.0] * 20
        score = score_metric_signal(
            history=history,
            current_value=91.3,
            threshold_value=90.0,
            alarm_state="ALARM",
        )
        # breach_score = min(0.0144, 1.0) = 0.0144; z-score tiny (std≈0)
        # blended ≈ 0.55*0.0144 ≈ 0.008; floor(ALARM, 91.3>90) → max(0.008, 0.55) = 0.55
        assert score >= 0.54

    def test_alarm_with_much_lower_history_scores_higher(self):
        """History of 50s; current is 91.3 — also a statistical outlier → higher score."""
        history_stable = [90.0] * 20
        history_low    = [50.0] * 20
        score_stable = score_metric_signal(
            history=history_stable, current_value=91.3,
            threshold_value=90.0, alarm_state="ALARM",
        )
        score_outlier = score_metric_signal(
            history=history_low, current_value=91.3,
            threshold_value=90.0, alarm_state="ALARM",
        )
        assert score_outlier >= score_stable


# ===========================================================================
# 6. score_metric_signal — missing values (graceful degradation)
# ===========================================================================

class TestMissingValues:
    def test_no_threshold_no_alarm_state_uses_statistics(self):
        """When only statistical info is available, fall back to z-score + EWMA."""
        # Use a wide-spread baseline so the small 10.5 increment doesn't
        # produce a high z-score.  Values spread from 5..15 give std ≈ 3.5.
        history = [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0,
                   5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0]
        score = score_metric_signal(
            history=history,
            current_value=10.5,
            threshold_value=None,
            alarm_state=None,
        )
        assert 0.0 <= score < 0.40, (
            f"Normal value should score below anomaly_threshold, got {score}"
        )

    def test_extreme_value_no_threshold_scores_high(self):
        history = [10.0] * 20
        score = score_metric_signal(
            history=history,
            current_value=200.0,
            threshold_value=None,
            alarm_state=None,
        )
        assert score >= 0.40

    def test_no_threshold_alarm_state_alarm_uses_stats_only(self):
        """ALARM state but no threshold → no breach score; statistics only."""
        history = [10.0] * 20
        score = score_metric_signal(
            history=history,
            current_value=12.0,   # barely above mean
            threshold_value=None,
            alarm_state="ALARM",  # explicit ALARM but no threshold to compute breach
        )
        # Without threshold, breach_score = 0 → pure stats path
        assert 0.0 <= score <= 1.0

    def test_no_value_no_history_returns_zero(self):
        """Empty history, no breach context → score near zero."""
        score = score_metric_signal(
            history=[],
            current_value=91.3,
            threshold_value=None,
            alarm_state=None,
        )
        # z-score requires ≥2 points; EWMA of single value = itself → dev = 0
        assert score == 0.0


# ===========================================================================
# 7. End-to-end: normalize then score (mimics _detect_and_score flow)
# ===========================================================================

class TestNormalizeAndScore:
    """Simulate the full path: raw CloudWatch payload → normalize → score."""

    def _score_from_payload(self, payload: dict, history: list[float] = None) -> float:
        sig = normalize_cloudwatch(payload)
        meta = sig.metadata
        alarm_state = meta.get("alarm_state")
        threshold_val = meta.get("threshold_value")
        return score_metric_signal(
            history=history or [],
            current_value=sig.value,
            threshold_value=threshold_val,
            alarm_state=alarm_state,
        )

    def test_ps_alarm_no_history_score_at_least_anomaly_threshold(self):
        """
        The PS database connection-pool alarm (91.3 vs 90) must produce
        a score ≥ the default anomaly_threshold (0.40) even with no history.
        """
        score = self._score_from_payload(_PS_ALARM_PAYLOAD, history=[])
        assert score >= 0.40, (
            f"PS ALARM event scored {score} — must be ≥ 0.40 (anomaly_threshold) "
            "even with no prior history"
        )

    def test_ps_alarm_score_reported(self, capsys):
        score = self._score_from_payload(_PS_ALARM_PAYLOAD, history=[])
        print(f"\nPS ALARM score (no history): {score:.4f}")
        assert score >= 0.55

    def test_ok_recovery_scores_zero(self):
        score = self._score_from_payload(_PS_OK_PAYLOAD)
        assert score == 0.0, (
            f"OK/recovery event must score 0.0, got {score}"
        )

    def test_ok_event_does_not_enter_anomaly_filter(self):
        """Ensure score < anomaly_threshold (0.40) so OK events are filtered."""
        from app.config import get_detection_cfg
        threshold = get_detection_cfg().get("anomaly_threshold", 0.40)
        score = self._score_from_payload(_PS_OK_PAYLOAD)
        assert score < threshold
