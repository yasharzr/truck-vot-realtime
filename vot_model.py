"""
VOT computation and MXL choice model from thesis.

Core idea:
- A truck approaching Toronto must choose: 401 (free, congested) or 407 (tolled, faster)
- The "market VOT" is what 407 effectively charges per hour of time saved
- The "thesis VOT" is what truck drivers are actually willing to pay (~$81/hr)
- The MXL model gives the probability of choosing the toll route given current conditions
"""

import math
import numpy as np
from scipy import stats
import config


def compute_vot_snapshot(
    tt_401: float,
    tt_407: float,
    delay_401: float,
    delay_407: float,
    toll_cost: float,
    distance_401_km: float,
    distance_407_km: float,
) -> dict:
    """
    Compute the full VOT analysis for current conditions.

    Args:
        tt_401: travel time on 401 in minutes
        tt_407: travel time on 407 in minutes
        delay_401: delay/variability on 401 in minutes
        delay_407: delay/variability on 407 in minutes
        toll_cost: current 407 toll in CAD
        distance_401_km: distance on 401 in km
        distance_407_km: distance on 407 in km

    Returns comprehensive analysis dict.
    """
    time_saved_min = tt_401 - tt_407
    extra_distance_km = max(0, distance_407_km - distance_401_km)

    # Market VOT: what 407 is effectively charging per hour of time saved
    if time_saved_min > 0:
        market_vot = (toll_cost / time_saved_min) * 60
    else:
        market_vot = float("inf")

    # Thesis VOT distribution
    m = config.MODEL
    vot_mean = m["vot_mean"]
    vot_sd = m["vot_sd"]

    # Percentage of truck population willing to pay the market VOT
    if market_vot < float("inf"):
        pct_willing = 1 - stats.norm.cdf(market_vot, loc=vot_mean, scale=vot_sd)
    else:
        pct_willing = 0.0

    # MXL choice probability (using mean coefficients)
    p_toll = _choice_probability(
        tt_401, tt_407, delay_401, delay_407, toll_cost, extra_distance_km
    )

    # Simulated MXL choice probability with random parameter draws
    p_toll_simulated = _simulated_choice_probability(
        tt_401, tt_407, delay_401, delay_407, toll_cost, extra_distance_km
    )

    # What toll SHOULD be to match thesis mean VOT
    if time_saved_min > 0:
        fair_toll = vot_mean * (time_saved_min / 60)
        overprice_pct = ((toll_cost - fair_toll) / fair_toll * 100) if fair_toll > 0 else 0
    else:
        fair_toll = 0
        overprice_pct = 0

    # Value of reliability comparison
    delay_saved_min = delay_401 - delay_407
    if delay_saved_min > 0:
        market_vor = (toll_cost / delay_saved_min) * 60
    else:
        market_vor = float("inf")

    return {
        "time_saved_minutes": round(time_saved_min, 1),
        "extra_distance_km": round(extra_distance_km, 1),
        "toll_cost": round(toll_cost, 2),
        "market_vot": round(market_vot, 2) if market_vot < float("inf") else None,
        "thesis_vot_mean": vot_mean,
        "thesis_vot_sd": vot_sd,
        "pct_willing": round(pct_willing * 100, 2),
        "choice_probability_toll": round(p_toll * 100, 2),
        "choice_probability_toll_simulated": round(p_toll_simulated * 100, 2),
        "fair_toll_at_mean_vot": round(fair_toll, 2),
        "overprice_pct": round(overprice_pct, 1),
        "market_vor": round(market_vor, 2) if market_vor < float("inf") else None,
        "thesis_vor_mean": m["vor_mean"],
        "delay_saved_minutes": round(delay_saved_min, 1),
        "verdict": _verdict(market_vot, vot_mean, time_saved_min),
    }


def _choice_probability(
    tt_401: float,
    tt_407: float,
    delay_401: float,
    delay_407: float,
    toll_cost: float,
    extra_dist_km: float,
) -> float:
    """MXL choice probability using mean parameter values."""
    m = config.MODEL
    v_free = m["beta_tt"] * tt_401 + m["beta_ttv"] * delay_401
    v_toll = (
        m["beta_tt"] * tt_407
        + m["beta_ttv"] * delay_407
        + m["beta_tc"] * toll_cost
        + m["beta_dist"] * extra_dist_km
    )
    diff = v_toll - v_free
    diff = max(-500, min(500, diff))
    return 1 / (1 + math.exp(-diff))


def _simulated_choice_probability(
    tt_401: float,
    tt_407: float,
    delay_401: float,
    delay_407: float,
    toll_cost: float,
    extra_dist_km: float,
    n_draws: int = 1000,
) -> float:
    """
    Simulated choice probability using random draws from parameter distributions.
    This captures the taste heterogeneity from the MXL model -- TT and TC are random.
    """
    m = config.MODEL
    rng = np.random.default_rng(42)

    beta_tt_draws = rng.normal(m["beta_tt"], m["beta_tt_sd"], n_draws)
    beta_tc_draws = rng.normal(m["beta_tc"], m["beta_tc_sd"], n_draws)
    beta_ttv = m["beta_ttv"]
    beta_dist = m["beta_dist"]

    v_free = beta_tt_draws * tt_401 + beta_ttv * delay_401
    v_toll = (
        beta_tt_draws * tt_407
        + beta_ttv * delay_407
        + beta_tc_draws * toll_cost
        + beta_dist * extra_dist_km
    )

    diff = np.clip(v_toll - v_free, -500, 500)
    probs = 1 / (1 + np.exp(-diff))
    return float(np.mean(probs))


def compute_24h_vot_projection(
    travel_times_24h: list[dict],
    tolls_24h: list[dict],
    distance_401_km: float = None,
    distance_407_km: float = None,
) -> list[dict]:
    """
    Combine 24h travel time and toll projections to produce VOT across the day.
    """
    if distance_401_km is None:
        distance_401_km = config.DISTANCE_401_KM
    if distance_407_km is None:
        distance_407_km = config.DISTANCE_407_KM

    extra_dist = max(0, distance_407_km - distance_401_km)
    results = []

    for tt_entry, toll_entry in zip(travel_times_24h, tolls_24h):
        tt_401 = tt_entry["tt_401"]
        tt_407 = tt_entry["tt_407"]
        time_saved = tt_401 - tt_407
        toll = toll_entry["toll_total"]

        delay_401 = max(0, tt_401 - config.FREEFLOW_401)
        delay_407 = max(0, tt_407 - config.FREEFLOW_407)

        if time_saved > 0:
            market_vot = (toll / time_saved) * 60
        else:
            market_vot = None

        p_toll = _choice_probability(
            tt_401, tt_407, delay_401, delay_407, toll, extra_dist
        )

        pct_willing = 0.0
        if market_vot is not None:
            pct_willing = 1 - stats.norm.cdf(
                market_vot, loc=config.MODEL["vot_mean"], scale=config.MODEL["vot_sd"]
            )

        results.append({
            "time_label": tt_entry["time_label"],
            "hour": tt_entry["hour"],
            "tt_401": tt_401,
            "tt_407": tt_407,
            "time_saved": round(time_saved, 1),
            "toll": toll,
            "time_period": toll_entry["time_period"],
            "market_vot": round(market_vot, 2) if market_vot else None,
            "choice_prob_toll": round(p_toll * 100, 2),
            "pct_willing": round(pct_willing * 100, 2),
        })

    return results


def _verdict(market_vot: float, thesis_vot: float, time_saved: float) -> str:
    if time_saved <= 0:
        return "401 is faster or equal right now — no benefit to taking 407"
    if market_vot == float("inf") or market_vot is None:
        return "Cannot compute market VOT — routes are equal speed"
    ratio = market_vot / thesis_vot
    if ratio <= 0.8:
        return f"407 is strong value right now — saving time at only ${market_vot:.0f}/hr"
    if ratio <= 1.0:
        return f"407 is reasonably priced at ${market_vot:.0f}/hr — good for time-sensitive loads"
    if ratio <= 1.5:
        return f"407 is moderately expensive at ${market_vot:.0f}/hr — weigh against your schedule pressure"
    return f"407 is costly at ${market_vot:.0f}/hr right now — only worth it for urgent loads"
