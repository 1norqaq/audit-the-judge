"""Negative control: equivalent answer pairs (no true quality difference).

Paper analogue: Y_clean strips the sensitive effect, and a calibrated audit must
NOT invent disparities. Here the null pairs are two samples of the same model on
the same question -- genuinely equivalent -- and a calibrated judge must NOT invent
a decisive preference. We report:

  * spurious_decisive_rate : P(verdict != tie) on null pairs, with a cluster
    bootstrap CI. This is the LLM-judge analogue of the false-flag rate P(S>=1).
  * side_skew              : among DECISIVE null verdicts, P(winner == ans1).
    ~0.5 means no content-side preference (ans1/ans2 are exchangeable samples).
  * a per-task breakdown for the FDR step.
"""
from __future__ import annotations

import pandas as pd

from stats import bootstrap_ci_over_pairs


def _decisive_rate(df: pd.DataFrame) -> float:
    return float((df["verdict_slot"] != "tie").mean())


def _side_skew(df: pd.DataFrame) -> float:
    dec = df[df["winner"].isin(["ans1", "ans2"])]
    if len(dec) == 0:
        return float("nan")
    return float((dec["winner"] == "ans1").mean())


def analyze(verdicts: pd.DataFrame, *, B: int = 2000, seed: int = 0) -> dict:
    null = verdicts[verdicts["pair_type"] == "null"].copy()
    if null.empty:
        raise ValueError("no null pairs in verdicts")

    overall = bootstrap_ci_over_pairs(null, _decisive_rate, B=B, seed=seed)
    skew = bootstrap_ci_over_pairs(null, _side_skew, B=B, seed=seed)

    per_task = {}
    tests = []
    for task, g in null.groupby("task"):
        ci = bootstrap_ci_over_pairs(g, _decisive_rate, B=B, seed=seed)
        per_task[task] = ci
        # FDR test = systematic content-side preference on equivalent pairs:
        # among decisive verdicts, is P(winner==ans1) different from 0.5?
        dec = g[g["winner"].isin(["ans1", "ans2"])]
        k = int((dec["winner"] == "ans1").sum())
        tests.append({"label": f"neg::{task}::side_skew", "k": k, "n": len(dec), "p_null": 0.5})

    return {
        "spurious_decisive_rate": overall,
        "side_skew": skew,
        "per_task": per_task,
        "tests": tests,  # side-skew vs 0.5, two-sided; feeds the BH-FDR table
        "n_null_tasks": len(null),
        "n_null_pairs": null["pair_id"].nunique(),
    }


if __name__ == "__main__":
    import sys

    from parse_outputs import load_verdicts

    res = analyze(load_verdicts(sys.argv[1]))
    print("spurious decisive rate:", res["spurious_decisive_rate"])
    print("side skew (P winner=ans1 | decisive):", res["side_skew"])
    for task, ci in res["per_task"].items():
        print(f"  {task:12s} {ci}")
