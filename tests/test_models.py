"""
Tests for Signal model — PRD §29 signal tests.
"""
import pytest
from datetime import datetime
from pydantic import ValidationError
from app.models.signal import Signal


def make_signal(**kwargs) -> Signal:
    defaults = dict(
        id="S1",
        timestamp=datetime(2026, 9, 12, 10, 0, 0),
        source="cloudwatch",
        environment="prod",
        service="payment",
        component="api",
        type="metric_anomaly",
    )
    defaults.update(kwargs)
    return Signal(**defaults)


def test_valid_signal():
    s = make_signal()
    assert s.id == "S1"
    assert s.environment == "prod"
    assert s.service == "payment"


def test_signal_with_optional_fields():
    s = make_signal(value=98.5, template_id="T001", message="DB timeout")
    assert s.value == 98.5
    assert s.template_id == "T001"
    assert s.message == "DB timeout"


def test_signal_optional_fields_default_none():
    s = make_signal()
    assert s.value is None
    assert s.template_id is None
    assert s.message is None


def test_invalid_timestamp():
    with pytest.raises((ValidationError, ValueError)):
        make_signal(timestamp="not-a-date")


def test_missing_required_field():
    with pytest.raises(ValidationError):
        Signal(
            id="S1",
            timestamp=datetime.utcnow(),
            source="cloudwatch",
            # environment missing
            service="payment",
            component="api",
            type="metric_anomaly",
        )
