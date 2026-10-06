"""Paired binary outcomes with conservative exact marginal interval bounds."""

import math
from typing import Any


def cdf(k: int, n: int, p: float) -> float:
    return math.fsum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def solve(k: int, n: int, target: float) -> float:
    low, high = 0.0, 1.0
    for _ in range(64):
        middle = (low + high) / 2
        if cdf(k, n, middle) > target:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def binomial_interval(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n < 1 or not 0 <= k <= n:
        raise ValueError("Invalid binomial counts.")
    lower = 0.0 if k == 0 else solve(k - 1, n, 1 - alpha / 2)
    upper = 1.0 if k == n else solve(k, n, alpha / 2)
    return lower, upper


def paired_evidence(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [
        p
        for p in pairs
        if type(p.get("control_success")) is bool and type(p.get("treatment_success")) is bool
    ]
    n = len(complete)
    if not n:
        return {
            "n": 0,
            "attempted": len(pairs),
            "missing": len(pairs),
            "effect": None,
            "interval": [-1, 1],
            "verdict": "insufficient evidence",
        }
    wins = sum(p["treatment_success"] and not p["control_success"] for p in complete)
    harms = sum(p["control_success"] and not p["treatment_success"] for p in complete)
    # Two 97.5% exact marginal intervals give simultaneous coverage >=95%.
    w_lo, w_hi = binomial_interval(wins, n, 0.025)
    h_lo, h_hi = binomial_interval(harms, n, 0.025)
    interval = [w_lo - h_hi, w_hi - h_lo]
    discordant = wins + harms
    p_value = (
        min(
            1.0,
            2 * sum(math.comb(discordant, i) for i in range(min(wins, harms) + 1)) / 2**discordant,
        )
        if discordant
        else 1.0
    )
    missing = len(pairs) - n
    # Worst-case bounds retain attempted pairs whose outcomes are unavailable.
    attempted = len(pairs)
    sensitivity = [(wins - harms - missing) / attempted, (wins - harms + missing) / attempted]
    return {
        "n": n,
        "attempted": attempted,
        "missing": missing,
        "control_rate": sum(p["control_success"] for p in complete) / n,
        "treatment_rate": sum(p["treatment_success"] for p in complete) / n,
        "wins": wins,
        "harms": harms,
        "effect": (wins - harms) / n,
        "interval": interval,
        "missing_outcome_bounds": sensitivity,
        "exact_p_value": p_value,
        "verdict": "improvement supported"
        if interval[0] > 0 and missing == 0
        else "harm supported"
        if interval[1] < 0 and missing == 0
        else "inconclusive",
    }
