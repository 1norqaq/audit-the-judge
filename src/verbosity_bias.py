"""Positive control, second axis: verbosity / length bias.

Same logic as position bias, different injected perturbation. On "verbose" pairs the
two answers are content-equivalent — a CONCISE answer (ans1) and a separately generated
DETAILED answer (ans2) to the same question, both asked to be correct and complete and
differing only in how thoroughly they explain. An unbiased judge should split 50/50; a
judge with length bias systematically prefers the longer (detailed) answer.

Because every verbose pair is shown in both orders, the LONGER answer (ans2) lands in
slot 1 half the time and slot 2 half the time, so this measure is orthogonal to
position bias: P(winner == ans2) isolates length preference.

  * verbosity_rate : among DECISIVE verbose-pair verdicts, P(judge picks the LONGER
    answer). 0.5 == unbiased; >0.5 == length bias. Tested vs 0.5 (binomial) for FDR.
"""
from __future__ import annotations

import pandas as pd

from stats import bootstrap_ci_over_pairs


def _longer_rate(df: pd.DataFrame) -> float:
    dec = df[df["winner"].isin(["ans1", "ans2"])]
    if len(dec) == 0:
        return float("nan")
    return float((dec["winner"] == "ans2").mean())  # ans2 is the detailed/longer answer


def analyze(verdicts: pd.DataFrame, *, B: int = 2000, seed: int = 0) -> dict:
    vb = verdicts[verdicts["pair_type"] == "verbose"].copy()
    if vb.empty:
        return {"verbosity_rate": None, "per_task": {}, "tests": [], "n_pairs": 0}

    overall = bootstrap_ci_over_pairs(vb, _longer_rate, B=B, seed=seed)

    per_task, tests = {}, []
    for task, g in vb.groupby("task"):
        per_task[task] = bootstrap_ci_over_pairs(g, _longer_rate, B=B, seed=seed)
        dec = g[g["winner"].isin(["ans1", "ans2"])]
        k = int((dec["winner"] == "ans2").sum())
        tests.append({"label": f"len::{task}::picks_longer", "k": k, "n": len(dec), "p_null": 0.5})

    return {
        "verbosity_rate": overall,
        "per_task": per_task,
        "tests": tests,
        "n_pairs": vb["pair_id"].nunique(),
    }


if __name__ == "__main__":
    import sys

    from parse_outputs import load_verdicts

    res = analyze(load_verdicts(sys.argv[1]))
    print("verbosity rate (P picks longer; 0.5=unbiased):", res["verbosity_rate"])
    for task, ci in res["per_task"].items():
        print(f"  {task:12s} {ci}")
