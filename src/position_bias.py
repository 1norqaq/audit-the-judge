"""Positive control: inject a KNOWN bias (presentation order) and check the audit flags it.

Paper analogue: Y_inject plants a fixed effect theta and the audit must recover it at
its advertised coverage. Order is a bias axis we control by construction -- every pair
is judged in both orders. A judge with no position bias is order-invariant. We report:

  * first_position_rate : among DECISIVE verdicts, P(judge picks the FIRST-shown answer).
    0.5 == unbiased; >0.5 == primacy bias. Tested against 0.5 (binomial) for the FDR step.
  * flip_rate           : fraction of pairs whose canonical winner changes when the order
    is swapped -- the direct "does the verdict survive a known perturbation" measure.
  * per-task first_position_rate for the FDR table.

Both read the per-pair table so the bootstrap resamples independent pairs.
"""
from __future__ import annotations

import pandas as pd

from stats import bootstrap_ci_rows


def build_pair_table(verdicts: pd.DataFrame) -> pd.DataFrame:
    """One row per pair: counts of first/second slot wins and the order-flip flag."""
    rows = []
    for pid, g in verdicts.groupby("pair_id"):
        slots = g["verdict_slot"].tolist()
        w = dict(zip(g["order"], g["winner"]))
        rows.append(
            {
                "pair_id": pid,
                "task": g["task"].iloc[0],
                "pair_type": g["pair_type"].iloc[0],
                "n_first": int(sum(s == "first" for s in slots)),
                "n_second": int(sum(s == "second" for s in slots)),
                "winner_AB": w.get("AB"),
                "winner_BA": w.get("BA"),
                "flip": (w.get("AB") is not None and w.get("BA") is not None and w["AB"] != w["BA"]),
                "complete": ("AB" in w and "BA" in w),
            }
        )
    return pd.DataFrame(rows)


def _first_position_rate(df: pd.DataFrame) -> float:
    dec = df["n_first"].sum() + df["n_second"].sum()
    return float(df["n_first"].sum() / dec) if dec else float("nan")


def _flip_rate(df: pd.DataFrame) -> float:
    comp = df[df["complete"]]
    return float(comp["flip"].mean()) if len(comp) else float("nan")


def analyze(verdicts: pd.DataFrame, *, B: int = 2000, seed: int = 0) -> dict:
    pt = build_pair_table(verdicts)
    # Primacy is measured cleanest on EQUIVALENT (null) pairs: there is no content
    # signal, so any first-slot tendency is pure position bias. On strong-vs-weak
    # pairs the judge should follow content, which would dilute the measure.
    null_pt = pt[pt["pair_type"] == "null"]

    fpr = bootstrap_ci_rows(null_pt, _first_position_rate, B=B, seed=seed)
    fpr_all = bootstrap_ci_rows(pt, _first_position_rate, B=B, seed=seed)
    flip = bootstrap_ci_rows(pt[pt["complete"]], _flip_rate, B=B, seed=seed)

    per_task, tests = {}, []
    for task, g in null_pt.groupby("task"):
        ci = bootstrap_ci_rows(g, _first_position_rate, B=B, seed=seed)
        per_task[task] = ci
        k = int(g["n_first"].sum())
        n = int(g["n_first"].sum() + g["n_second"].sum())
        tests.append({"label": f"pos::{task}::first_position", "k": k, "n": n, "p_null": 0.5})

    return {
        "first_position_rate": fpr,        # headline: on equivalent pairs
        "first_position_rate_all": fpr_all,  # secondary: across all pairs
        "flip_rate": flip,
        "per_task": per_task,
        "tests": tests,
        "pair_table": pt,
        "n_pairs": len(pt),
    }


if __name__ == "__main__":
    import sys

    from parse_outputs import load_verdicts

    res = analyze(load_verdicts(sys.argv[1]))
    print("first-position rate (0.5=unbiased):", res["first_position_rate"])
    print("flip rate:", res["flip_rate"])
    for task, ci in res["per_task"].items():
        print(f"  {task:12s} {ci}")
