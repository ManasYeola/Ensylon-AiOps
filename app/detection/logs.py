"""
Log anomaly detection using Drain3 template extraction + burst detection.
Pipeline: raw log → template ID → frequency tracking → burst detection → anomaly signal
PRD §11
"""
from collections import defaultdict
from typing import Optional

try:
    from drain3 import TemplateMiner
    from drain3.template_miner_config import TemplateMinerConfig
    DRAIN3_AVAILABLE = True
except ImportError:
    DRAIN3_AVAILABLE = False


# Global template miner (singleton for replay scenarios)
_template_miner: Optional[object] = None


def _get_template_miner():
    global _template_miner
    if _template_miner is None:
        if DRAIN3_AVAILABLE:
            try:
                config = TemplateMinerConfig()
                _template_miner = TemplateMiner(config=config)
            except Exception:
                # Fallback if Drain3 API differs from expected
                _template_miner = _FallbackMiner()
        else:
            _template_miner = _FallbackMiner()
    return _template_miner


class _FallbackMiner:
    """
    Trivial fallback when Drain3 is not installed.
    Groups identical messages and assigns them the same template.
    """
    def __init__(self):
        self._templates: dict[str, str] = {}
        self._counter = 0

    def add_log_message(self, log_line: str) -> dict:
        # Normalize: strip trailing numbers/IDs to produce a rough template
        import re
        template = re.sub(r"\b\d+\b", "<*>", log_line).strip()
        if template not in self._templates:
            self._counter += 1
            self._templates[template] = f"T{self._counter:03d}"
        return {"template_mined": template, "cluster_id": self._templates[template]}


def extract_template(log_message: str) -> tuple[str, str]:
    """
    Extract (template_id, template_text) from a raw log message.
    Uses Drain3 if available, otherwise uses fallback regex normalizer.
    """
    miner = _get_template_miner()
    result = miner.add_log_message(log_message)
    if DRAIN3_AVAILABLE and not isinstance(result, dict):
        # Drain3 object-based API
        cluster_id = str(result.cluster_id)
        template = result.get_template()
    else:
        # Fallback (dict-based) or older Drain3
        cluster_id = result["cluster_id"]
        template = result["template_mined"]
    return cluster_id, template


def detect_log_burst(
    template_id: str,
    frequency_counter: dict[str, int],
    baseline: dict[str, float],
    burst_multiplier: float = 3.0,
) -> bool:
    """
    Returns True if the template occurrence rate exceeds the baseline by burst_multiplier.
    baseline[template_id] = expected frequency count per window.
    """
    current = frequency_counter.get(template_id, 0)
    expected = baseline.get(template_id, 1.0)   # treat unknown templates with low baseline
    return current >= expected * burst_multiplier


def build_frequency_counter(messages: list[str]) -> tuple[dict[str, int], dict]:
    """
    Process a list of log messages through the template miner.
    Returns (frequency_counter, template_map).
    frequency_counter: template_id → count
    template_map: template_id → template_text
    """
    counter: dict[str, int] = defaultdict(int)
    template_map: dict[str, str] = {}

    for msg in messages:
        tid, tmpl = extract_template(msg)
        counter[tid] += 1
        template_map[tid] = tmpl

    return dict(counter), template_map
