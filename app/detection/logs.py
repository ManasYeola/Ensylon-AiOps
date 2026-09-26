"""
Log anomaly detection — Drain3 template extraction + sliding-window burst scoring.

Pipeline: raw log evidence (PII-redacted) → template ID → windowed frequency
          → burst ratio vs learned baseline → anomaly_score

Key public API
--------------
LogWindowState          Per-service sliding-window frequency tracker.
score_log_signal(message, state) → (float, str, str)   [score, tid, template]
extract_template(log_message)    → (template_id, template_text)
build_frequency_counter(messages) → (counter, template_map)   [kept for tests]
detect_log_burst(...)            → bool   [legacy gate; kept for tests]

Window / baseline settings (from config.yaml detection section)
----------------------------------------------------------------
  log_window_seconds      (int, default 300)   Length of the sliding count window.
                          Counts older than this are discarded.
  log_bucket_seconds      (int, default 60)    Resolution of time buckets.
                          Each bucket accumulates counts for one period.
                          Buckets expire when the oldest edge leaves the window.
  log_baseline_windows    (int, default 5)     Number of complete windows to
                          use for computing the baseline count.
                          The baseline for each template is:
                              mean(counts per window over last N windows)
                          A template seen for the first time has baseline = 1.
  log_burst_multiplier    (float, default 3.0) Ratio of current_window_count
                          to baseline at which a burst is declared (score → 0.5).
"""
from collections import defaultdict, deque
from typing import Optional
import time

try:
    from drain3 import TemplateMiner
    from drain3.template_miner_config import TemplateMinerConfig
    DRAIN3_AVAILABLE = True
except ImportError:
    DRAIN3_AVAILABLE = False


# ---------------------------------------------------------------------------
# Drain3 singleton (shared across all LogWindowState instances)
# ---------------------------------------------------------------------------

_template_miner: Optional[object] = None


def _get_template_miner():
    global _template_miner
    if _template_miner is None:
        if DRAIN3_AVAILABLE:
            try:
                config = TemplateMinerConfig()
                _template_miner = TemplateMiner(config=config)
            except Exception:
                _template_miner = _FallbackMiner()
        else:
            _template_miner = _FallbackMiner()
    return _template_miner


class _FallbackMiner:
    """
    Trivial fallback when Drain3 is not installed.
    Groups messages by regex-normalised form and assigns stable template IDs.
    """
    def __init__(self):
        self._templates: dict[str, str] = {}
        self._counter = 0

    def add_log_message(self, log_line: str) -> dict:
        import re
        template = re.sub(r"\b\d+\b", "<*>", log_line).strip()
        if template not in self._templates:
            self._counter += 1
            self._templates[template] = f"T{self._counter:03d}"
        return {"template_mined": template, "cluster_id": self._templates[template]}


def extract_template(log_message: str) -> tuple[str, str]:
    """
    Extract (template_id, template_text) from a log message.
    PII must have been redacted BEFORE calling this function.
    """
    miner = _get_template_miner()
    result = miner.add_log_message(log_message)
    if DRAIN3_AVAILABLE and not isinstance(result, dict):
        # Drain3 object-based API
        cluster_id = str(result.cluster_id)
        template = result.get_template()
    else:
        cluster_id = result["cluster_id"]
        template = result["template_mined"]
    return cluster_id, template


# ---------------------------------------------------------------------------
# Sliding-window state (one per service)
# ---------------------------------------------------------------------------

class LogWindowState:
    """
    Per-service, sliding time-bucket frequency tracker for Drain3 templates.

    Design
    ------
    Time is divided into fixed-size *buckets* of `bucket_seconds`.
    Each bucket is a dict {template_id: count}.
    The deque holds (bucket_start_epoch, counter_dict) pairs, newest last.

    On every call to `record()`:
      1. Expire buckets whose start_epoch < now - window_seconds.
      2. Append counts to the current (newest) bucket; create one if needed.

    Baseline
    --------
    The baseline for each template is the **mean count per window** observed
    over the last `baseline_windows` complete windows.

    "Complete window" = a chunk of exactly `window_seconds` worth of history
    accumulated before the current window. During warm-up (fewer than
    `baseline_windows` worth of data) the baseline gracefully degrades to the
    actual mean of available data, with a floor of 1.

    This means:
      - A template recurring every window (e.g., a health-check) will develop
        a baseline ≈ its normal rate, and will NOT be flagged as a burst.
      - A sudden spike of 10× the baseline will score ≥ 0.5.
      - Counts from old windows are discarded — the scorer cannot accumulate
        lifetime counts.

    Parameters (all read from config.yaml at construction time if not supplied)
    ---------------------------------------------------------------------------
    window_seconds      : Sliding window width (seconds).  Default 300 (5 min).
    bucket_seconds      : Time-bucket resolution.  Default 60 (1 min).
    baseline_windows    : How many complete windows to average for baseline.
                          Default 5.
    burst_multiplier    : Ratio current/baseline at which score reaches 0.5.
                          Default 3.0.
    _clock              : Callable returning current epoch time (injectable for
                          testing without sleeping).
    """

    def __init__(
        self,
        window_seconds: int = 300,
        bucket_seconds: int = 60,
        baseline_windows: int = 5,
        burst_multiplier: float = 3.0,
        _clock=None,
    ):
        self.window_seconds = window_seconds
        self.bucket_seconds = bucket_seconds
        self.baseline_windows = baseline_windows
        self.burst_multiplier = burst_multiplier
        self._clock = _clock or time.time

        # deque of (bucket_start: float, counts: dict[tid, int])
        # newest bucket is at the right
        self._buckets: deque[tuple[float, dict[str, int]]] = deque()

        # Historical per-window totals for baseline learning
        # deque of dict[tid, int] — one entry per complete window
        self._completed_windows: deque[dict[str, int]] = deque(maxlen=baseline_windows)

        # Template ID → template text (for evidence strings)
        self.template_texts: dict[str, str] = {}

    # ── Internal helpers ────────────────────────────────────────────────────

    def _now(self) -> float:
        return self._clock()

    def _current_bucket_start(self, now: float) -> float:
        return (now // self.bucket_seconds) * self.bucket_seconds

    def _expire(self, now: float) -> None:
        """Drop buckets whose start_epoch is older than the window."""
        cutoff = now - self.window_seconds
        while self._buckets and self._buckets[0][0] < cutoff:
            self._buckets.popleft()

    def _window_counts(self) -> dict[str, int]:
        """Aggregate counts across all current (unexpired) buckets."""
        totals: dict[str, int] = defaultdict(int)
        for _, bucket_counts in self._buckets:
            for tid, cnt in bucket_counts.items():
                totals[tid] += cnt
        return dict(totals)

    def _baseline(self, tid: str) -> float:
        """
        Compute the expected count for `tid` over one window.
        Uses the mean of the last `baseline_windows` complete-window snapshots.
        Falls back to the current-window count (floor 1) when no history.
        """
        if not self._completed_windows:
            return 1.0
        total = sum(w.get(tid, 0) for w in self._completed_windows)
        n = len(self._completed_windows)
        return max(total / n, 1.0)

    # ── Public API ──────────────────────────────────────────────────────────

    def record(self, tid: str, template_text: str) -> tuple[int, float]:
        """
        Record one occurrence of `tid` at the current time.
        Returns (current_window_count, baseline_count).
        Expires old buckets and archives completed windows as a side effect.
        """
        now = self._now()
        self._expire(now)
        self.template_texts[tid] = template_text

        bucket_start = self._current_bucket_start(now)

        # Get or create the current bucket
        if not self._buckets or self._buckets[-1][0] != bucket_start:
            # A new bucket has started — archive the just-finished window snapshot
            if self._buckets:
                snapshot = self._window_counts()
                if snapshot:
                    self._completed_windows.append(snapshot)
            self._buckets.append((bucket_start, {}))

        self._buckets[-1][1][tid] = self._buckets[-1][1].get(tid, 0) + 1

        current = self._window_counts().get(tid, 0)
        baseline = self._baseline(tid)
        return current, baseline

    def current_window_count(self, tid: str) -> int:
        """Snapshot of unexpired count for `tid` without recording anything."""
        now = self._now()
        self._expire(now)
        return self._window_counts().get(tid, 0)


# ---------------------------------------------------------------------------
# Scoring function — pure given a LogWindowState
# ---------------------------------------------------------------------------

def score_log_signal(
    message: str,
    state: "LogWindowState",
) -> tuple[float, str, str]:
    """
    Compute anomaly_score (0.0–1.0) for a log signal.

    The message MUST have been PII-redacted before calling this function.
    Template IDs are derived from the redacted text so no PII enters the
    Drain3 model or the frequency state.

    Score mapping (ratio = current_window_count / baseline_per_window):
        ratio < 1.0              → 0.0   (below or at normal rate)
        1.0 ≤ ratio < burst_mult → 0.0–0.5  (elevated, linear ramp)
        burst_mult ≤ ratio < 2×  → 0.5–0.8  (confirmed burst)
        ratio ≥ 2×burst_mult     → 0.8–1.0  (severe burst, capped at 1.0)

    Returns (anomaly_score, template_id, template_text).
    """
    tid, template_text = extract_template(message)
    current, baseline = state.record(tid, template_text)

    ratio = current / max(baseline, 1.0)
    burst_mult = state.burst_multiplier

    if ratio < 1.0:
        score = 0.0
    elif ratio < burst_mult:
        score = 0.5 * (ratio - 1.0) / max(burst_mult - 1.0, 1e-9)
    elif ratio < burst_mult * 2:
        score = 0.5 + 0.3 * (ratio - burst_mult) / max(burst_mult, 1e-9)
    else:
        score = min(0.8 + 0.2 * (ratio - burst_mult * 2) / max(burst_mult * 2, 1e-9), 1.0)

    return round(score, 4), tid, template_text


# ---------------------------------------------------------------------------
# Factory — construct LogWindowState from config.yaml
# ---------------------------------------------------------------------------

def make_log_window_state(_clock=None) -> "LogWindowState":
    """
    Build a LogWindowState using parameters from config.yaml detection section.
    Injects a custom clock for testing.
    """
    from app.config import get_detection_cfg
    cfg = get_detection_cfg()
    return LogWindowState(
        window_seconds=int(cfg.get("log_window_seconds", 300)),
        bucket_seconds=int(cfg.get("log_bucket_seconds", 60)),
        baseline_windows=int(cfg.get("log_baseline_windows", 5)),
        burst_multiplier=float(cfg.get("log_burst_multiplier", 3.0)),
        _clock=_clock,
    )


# ---------------------------------------------------------------------------
# Legacy API — kept so existing tests continue to pass
# ---------------------------------------------------------------------------

def detect_log_burst(
    template_id: str,
    frequency_counter: dict[str, int],
    baseline: dict[str, float],
    burst_multiplier: float = 3.0,
) -> bool:
    """
    Legacy burst gate — returns True if count exceeds baseline * multiplier.
    Used only by existing unit tests; new code uses LogWindowState.
    """
    current = frequency_counter.get(template_id, 0)
    expected = baseline.get(template_id, 1.0)
    return current >= expected * burst_multiplier


def build_frequency_counter(messages: list[str]) -> tuple[dict[str, int], dict]:
    """
    Process a list of log messages through the template miner.
    Returns (frequency_counter, template_map). Kept for existing unit tests.
    """
    counter: dict[str, int] = defaultdict(int)
    template_map: dict[str, str] = {}
    for msg in messages:
        tid, tmpl = extract_template(msg)
        counter[tid] += 1
        template_map[tid] = tmpl
    return dict(counter), template_map
