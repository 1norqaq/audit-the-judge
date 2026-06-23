"""Uncertainty quantification for the judge audit.

Two tools, both straight from the paper's playbook:

  * bootstrap_ci  -- the verdict is a *distribution*, not a single number. We
    resample the unit of independence (the PAIR, not the row: a pair's two
    presentation orders are dependent) and recompute each rate, then take
    percentile CIs.

  * fdr_table     -- when we test many tasks/dimensions at once, control the
    Benjamini-Hochberg false discovery rate (statsmodels multipletests).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from statsmodels.stats.multitest import multipletests


@dataclass
class CI:
    point: float
    lo: float
    hi: float
    n: int

    def __repr__(self) -> str:
        return f"{self.point:.3f} [{self.lo:.3f}, {self.hi:.3f}] (n={self.n})"


def bootstrap_ci_over_pairs(
    df: pd.DataFrame,
    stat_fn,
    *,
    pair_col: str = "pair_id",
    B: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> CI:
    """Cluster-bootstrap a statistic by resampling whole pairs with replacement.

    stat_fn(sub_df) -> float, computed on the full data and on each resample.
    Returns the point estimate and the (alpha/2, 1-alpha/2) percentile interval.
    """
    rng = np.random.default_rng(seed)
    pairs = df[pair_col].unique()
    groups = {p: g for p, g in df.groupby(pair_col)}
    point = float(stat_fn(df))
    boot = np.empty(B)
    for b in range(B):
        sample = rng.choice(pairs, size=len(pairs), replace=True)
        resampled = pd.concat([groups[p] for p in sample], ignore_index=True)
        boot[b] = stat_fn(resampled)
    lo, hi = np.percentile(boot, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return CI(point=point, lo=float(lo), hi=float(hi), n=len(pairs))


def bootstrap_ci_rows(
    df: pd.DataFrame, stat_fn, *, B: int = 2000, alpha: float = 0.05, seed: int = 0
) -> CI:
    """Plain nonparametric bootstrap over independent ROWS.

    Use when each row is already one independent unit (e.g. a per-pair summary
    table, one row per pair). stat_fn(sub_df) -> float.
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    point = float(stat_fn(df))
    idx = np.arange(n)
    boot = np.empty(B)
    for b in range(B):
        boot[b] = stat_fn(df.iloc[rng.choice(idx, size=n, replace=True)])
    lo, hi = np.percentile(boot, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return CI(point=point, lo=float(lo), hi=float(hi), n=n)


def fdr_table(tests: list[dict], alpha: float = 0.05) -> pd.DataFrame:
    """Apply Benjamini-Hochberg across a list of binomial tests.

    Each test: {label, k, n, p_null}  (k successes of n vs null prob p_null,
    two-sided). Returns a tidy table with raw p, BH q, and significance flag.
    """
    rows = []
    for t in tests:
        res = binomtest(int(t["k"]), int(t["n"]), t.get("p_null", 0.5), alternative="two-sided")
        rows.append(
            {
                "label": t["label"],
                "k": int(t["k"]),
                "n": int(t["n"]),
                "rate": t["k"] / t["n"] if t["n"] else float("nan"),
                "p_null": t.get("p_null", 0.5),
                "p_raw": res.pvalue,
            }
        )
    df = pd.DataFrame(rows)
    if len(df):
        rej, q, _, _ = multipletests(df["p_raw"].values, alpha=alpha, method="fdr_bh")
        df["q_bh"] = q
        df["sig_fdr"] = rej
    return df
