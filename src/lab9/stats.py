"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _norm(labels: Sequence[str]) -> list[str]:
    return [str(x).strip().upper() for x in labels]


def _paired(human: Sequence[str], judge: Sequence[str]) -> tuple[list[str], list[str]]:
    h, j = _norm(human), _norm(judge)
    if len(h) != len(j):
        raise ValueError(f"human has {len(h)} labels, judge has {len(j)}: not the same items")
    if not h:
        raise ValueError("no labels")
    return h, j


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    h, j = _paired(human, judge)
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for hv, jv in zip(h, j):
        if jv == POS:
            cm["tp" if hv == POS else "fp"] += 1
        else:
            cm["fn" if hv == POS else "tn"] += 1
    return cm


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    p_den, r_den = cm["tp"] + cm["fp"], cm["tp"] + cm["fn"]
    precision = cm["tp"] / p_den if p_den else 0.0
    recall = cm["tp"] / r_den if r_den else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    h, j = _paired(human, judge)
    n = len(h)
    p_o = sum(hv == jv for hv, jv in zip(h, j)) / n
    p_e = sum((h.count(c) / n) * (j.count(c) / n) for c in set(h) | set(j))
    if math.isclose(p_e, 1.0, abs_tol=1e-12):
        raise ValueError("kappa undefined: expected agreement is 1 (both raters constant)")
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1].
    Returns nan when sensitivity + specificity == 1: such a judge is no better than a coin,
    and its observed rate carries no information about the true rate."""
    denom = sensitivity + specificity - 1
    if math.isclose(denom, 0.0, abs_tol=1e-12):
        return float("nan")
    corrected = (observed_rate + specificity - 1) / denom
    return min(1.0, max(0.0, corrected))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy.stats import bootstrap

    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if x.shape != y.shape or x.ndim != 1:
        raise ValueError(f"paired bootstrap needs two 1-D samples of equal length, got {x.shape} and {y.shape}")
    if x.size == 0:
        return (0.0, 0.0, 0.0)          # no shared items: a == b vacuously; floors still apply
    if not (np.all(np.isfinite(x)) and np.all(np.isfinite(y))):
        raise ValueError("paired bootstrap got NaN/inf: refuse to compare broken per-item scores")
    if np.array_equal(x, y):
        return (0.0, 0.0, 0.0)
    diff = float(x.mean() - y.mean())
    d = x - y
    if x.size < 2 or np.all(d == d[0]):
        # Every resample gives the same difference: the CI collapses to the point estimate.
        return (diff, diff, diff)

    def stat(p, q, axis=-1):
        return np.mean(p, axis=axis) - np.mean(q, axis=axis)

    res = bootstrap((x, y), stat, paired=True, vectorized=True, n_resamples=n_resamples,
                    confidence_level=confidence, method="percentile", rng=np.random.default_rng(rng))
    return (diff, float(res.confidence_interval.low), float(res.confidence_interval.high))


def _check_nck(n: int, c: int, k: int) -> tuple[int, int, int]:
    for name, v in (("n", n), ("c", c), ("k", k)):
        if isinstance(v, bool) or not isinstance(v, numbers.Integral):
            raise ValueError(f"{name}={v!r} must be an integer")
    n, c, k = int(n), int(c), int(k)
    if n < 1:
        raise ValueError(f"n={n}: need at least one trial")
    if not 0 <= c <= n:
        raise ValueError(f"c={c} must be between 0 and n={n}")
    if not 1 <= k <= n:
        raise ValueError(f"k={k} must be between 1 and n={n}")
    return n, c, k


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    n, c, k = _check_nck(n, c, k)
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    n, c, k = _check_nck(n, c, k)
    return math.comb(c, k) / math.comb(n, k)
