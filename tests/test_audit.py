"""Verification with no API key required.

Plants a KNOWN judge behavior into a synthetic verdict table and checks that the
audit recovers it — the positive-control sanity check applied to our own tooling:

  * a biased judge (70% primacy) -> first-position CI excludes 0.5 AND is FDR-significant
  * a calibrated judge (50/50, mostly ties on equivalent pairs) -> CI includes 0.5,
    low spurious decisive rate, no FDR-significant flags.

Run:  python tests/test_audit.py     (plain asserts; also works under pytest)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import negative_control  # noqa: E402
import position_bias  # noqa: E402
import verbosity_bias  # noqa: E402
from parse_outputs import _winner  # noqa: E402
from stats import fdr_table  # noqa: E402

TASKS = ["knowledge", "reasoning", "writing", "coding"]


def _slot_for_winner(order, winner):
    """Inverse of parse_outputs._winner: which slot must hold this canonical winner."""
    if winner == "tie":
        return "tie"
    if order == "AB":
        return "first" if winner == "ans1" else "second"
    return "second" if winner == "ans1" else "first"


def synth_verdicts(n_pairs=200, p_first=0.5, p_tie_null=0.6, acc_nonnull=0.9,
                   p_longer=0.5, p_tie_verbose=0.45, seed=0):
    """Build a tidy verdict table for a judge with controllable behavior.

    p_first      : P(pick FIRST slot | decisive)            -> primacy bias (0.5 = none)
    p_tie_null   : P(tie) on equivalent (null) pairs        -> calibration to genuine ties
    acc_nonnull  : P(prefer the strong answer) on nonnull   -> quality discrimination
    p_longer     : P(pick the LONGER answer | decisive) on verbose pairs (0.5 = no length bias)
    p_tie_verbose: P(tie) on verbose pairs
    """
    rng = np.random.default_rng(seed)
    rows = []

    def decisive_slot():
        return "first" if rng.random() < p_first else "second"

    for i in range(n_pairs):
        task = TASKS[i % len(TASKS)]
        # null pair: equivalent answers
        for order in ("AB", "BA"):
            slot = "tie" if rng.random() < p_tie_null else decisive_slot()
            rows.append(_row(f"p{i}::null", task, "null", "tie", order, slot))
        # nonnull pair: ans1 is the strong answer
        for order in ("AB", "BA"):
            if rng.random() < acc_nonnull:
                slot = _slot_for_winner(order, "ans1")
            else:
                slot = decisive_slot()
            rows.append(_row(f"p{i}::nonnull", task, "nonnull", "ans1", order, slot))
        # verbose pair: ans2 is the longer (detailed) answer; content-equivalent
        for order in ("AB", "BA"):
            if rng.random() < p_tie_verbose:
                slot = "tie"
            else:
                winner = "ans2" if rng.random() < p_longer else "ans1"
                slot = _slot_for_winner(order, winner)
            rows.append(_row(f"p{i}::verbose", task, "verbose", "tie", order, slot))
    return pd.DataFrame(rows)


def _row(pid, task, ptype, true_label, order, slot):
    return {
        "pair_id": pid, "task": task, "pair_type": ptype, "true_label": true_label,
        "order": order, "verdict_slot": slot, "winner": _winner(order, slot),
    }


def test_biased_judge_is_flagged():
    v = synth_verdicts(n_pairs=240, p_first=0.70, seed=1)
    pos = position_bias.analyze(v, B=1000, seed=1)
    fpr = pos["first_position_rate"]
    assert fpr.lo > 0.5, f"planted 0.70 primacy not detected: {fpr}"
    fdr = fdr_table(pos["tests"])
    assert fdr["sig_fdr"].any(), "biased judge produced no FDR-significant task"
    print("OK biased judge flagged:", fpr, "| FDR sig:", int(fdr["sig_fdr"].sum()), "/", len(fdr))


def test_length_bias_is_flagged():
    v = synth_verdicts(n_pairs=240, p_longer=0.75, seed=4)
    vb = verbosity_bias.analyze(v, B=1000, seed=4)
    vr = vb["verbosity_rate"]
    assert vr.lo > 0.5, f"planted 0.75 length bias not detected: {vr}"
    fdr = fdr_table(vb["tests"])
    assert fdr["sig_fdr"].any(), "length-biased judge produced no FDR-significant task"
    print("OK length bias flagged:", vr, "| FDR sig:", int(fdr["sig_fdr"].sum()), "/", len(fdr))


def test_calibrated_judge_passes():
    v = synth_verdicts(n_pairs=240, p_first=0.50, p_tie_null=0.7, p_longer=0.50, seed=2)
    neg = negative_control.analyze(v, B=1000, seed=2)
    pos = position_bias.analyze(v, B=1000, seed=2)
    vb = verbosity_bias.analyze(v, B=1000, seed=2)
    fpr, vr = pos["first_position_rate"], vb["verbosity_rate"]
    assert fpr.lo <= 0.5 <= fpr.hi, f"calibrated judge wrongly flagged for primacy: {fpr}"
    assert vr.lo <= 0.5 <= vr.hi, f"calibrated judge wrongly flagged for length: {vr}"
    assert neg["side_skew"].lo <= 0.5 <= neg["side_skew"].hi, f"spurious side skew: {neg['side_skew']}"
    assert neg["spurious_decisive_rate"].point < 0.45, neg["spurious_decisive_rate"]
    fdr = fdr_table(neg["tests"] + pos["tests"] + vb["tests"])
    assert not fdr["sig_fdr"].any(), f"calibrated judge produced false flags:\n{fdr}"
    print("OK calibrated judge passes:", fpr, "| len:", vr, "| decisive:", neg["spurious_decisive_rate"])


def test_discrimination_recovered():
    v = synth_verdicts(n_pairs=200, acc_nonnull=0.9, seed=3)
    nn = v[(v["pair_type"] == "nonnull") & (v["winner"].isin(["ans1", "ans2"]))]
    acc = (nn["winner"] == "ans1").mean()
    assert acc > 0.8, f"discrimination not recovered: {acc:.3f}"
    print(f"OK discrimination recovered: {acc:.3f}")


if __name__ == "__main__":
    test_biased_judge_is_flagged()
    test_length_bias_is_flagged()
    test_calibrated_judge_passes()
    test_discrimination_recovered()
    print("\nALL FIXTURE CHECKS PASSED")
