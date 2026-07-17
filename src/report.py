"""Assemble the one-page Judge Trustworthiness Report.

Runs both control axes (position + verbosity), the negative control, the
discrimination sanity check, bootstrap CIs, and the BH-FDR table, then writes:
    <outdir>/figures/negative_control.png
    <outdir>/figures/position_bias.png
    <outdir>/figures/verbosity_bias.png
    <outdir>/judge_trust_report.md

Usage:
    python src/report.py <verdicts.jsonl | oc_results_dir> [--model NAME] [--B 2000] [--outdir DIR]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import negative_control  # noqa: E402
import position_bias  # noqa: E402
import verbosity_bias  # noqa: E402
from parse_outputs import load_verdicts  # noqa: E402
from stats import CI, bootstrap_ci_over_pairs, fdr_table  # noqa: E402


def discrimination_accuracy(verdicts: pd.DataFrame, *, B: int, seed: int) -> CI:
    """On non-null pairs (ans1=strong, ans2=weak), how often does the judge pick the
    strong answer? Should be high — confirms the judge is not simply random."""
    nn = verdicts[(verdicts["pair_type"] == "nonnull") & (verdicts["winner"].isin(["ans1", "ans2"]))]
    return bootstrap_ci_over_pairs(nn, lambda d: float((d["winner"] == "ans1").mean()), B=B, seed=seed)


def compute_metrics(verdicts: pd.DataFrame, *, B: int = 2000, seed: int = 0) -> dict:
    """Run every control axis on one judge's verdict table and return the raw results.

    Shared by the single-judge report (write_report + make_figures below) and the
    multi-judge comparison (compare_report.py), so both read identical numbers.
    """
    neg = negative_control.analyze(verdicts, B=B, seed=seed)
    pos = position_bias.analyze(verdicts, B=B, seed=seed)
    vb = verbosity_bias.analyze(verdicts, B=B, seed=seed)
    disc = discrimination_accuracy(verdicts, B=B, seed=seed)
    fdr = fdr_table(neg["tests"] + pos["tests"] + vb["tests"])
    return {"neg": neg, "pos": pos, "vb": vb, "disc": disc, "fdr": fdr, "has_verbose": vb["n_pairs"] > 0}


def _bar_with_ci(ax, labels, cis, ref, ref_label, title, ylabel, color="#4C72B0"):
    xs = range(len(labels))
    pts = [c.point for c in cis]
    lo = [c.point - c.lo for c in cis]
    hi = [c.hi - c.point for c in cis]
    ax.bar(xs, pts, color=color, alpha=0.85)
    ax.errorbar(xs, pts, yerr=[lo, hi], fmt="none", ecolor="black", capsize=4, lw=1.2)
    if ref is not None:
        ax.axhline(ref, ls="--", color="#C44E52", lw=1.3, label=ref_label)
        ax.legend(loc="upper right", fontsize=8)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.set_ylim(0, 1)


def make_figures(neg: dict, pos: dict, vb: dict, fig_dir: Path):
    fig_dir.mkdir(parents=True, exist_ok=True)

    # Negative control: spurious decisive rate per task (lower is better)
    tasks = list(neg["per_task"].keys())
    fig, ax = plt.subplots(figsize=(6, 3.6))
    _bar_with_ci(ax, tasks, [neg["per_task"][t] for t in tasks], None, None,
                 "Negative control: spurious decisive rate on equivalent pairs",
                 "P(verdict != tie)")
    ax.axhline(neg["spurious_decisive_rate"].point, ls=":", color="gray", lw=1,
               label=f"overall {neg['spurious_decisive_rate'].point:.2f}")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout(); fig.savefig(fig_dir / "negative_control.png", dpi=140); plt.close(fig)

    # Positive control axis 1: first-position rate per task (0.5 = unbiased)
    tasks = list(pos["per_task"].keys())
    fig, ax = plt.subplots(figsize=(6, 3.6))
    _bar_with_ci(ax, tasks, [pos["per_task"][t] for t in tasks], 0.5, "unbiased (0.5)",
                 "Positive control 1: first-position rate on equivalent pairs (primacy)",
                 "P(judge picks first-shown)", color="#55A868")
    fig.tight_layout(); fig.savefig(fig_dir / "position_bias.png", dpi=140); plt.close(fig)

    # Positive control axis 2: verbosity (length) bias per task (0.5 = unbiased)
    if vb["per_task"]:
        tasks = list(vb["per_task"].keys())
        fig, ax = plt.subplots(figsize=(6, 3.6))
        _bar_with_ci(ax, tasks, [vb["per_task"][t] for t in tasks], 0.5, "unbiased (0.5)",
                     "Positive control 2: prefers-longer rate on concise-vs-detailed pairs",
                     "P(judge picks longer answer)", color="#8172B3")
        fig.tight_layout(); fig.savefig(fig_dir / "verbosity_bias.png", dpi=140); plt.close(fig)


def write_report(neg, pos, vb, disc, fdr, model, B, report_path: Path, has_verbose: bool):
    sdr, fpr, flip = neg["spurious_decisive_rate"], pos["first_position_rate"], pos["flip_rate"]
    n_sig = int(fdr["sig_fdr"].sum()) if len(fdr) else 0

    def fmt(ci) -> str:
        return f"{ci.point:.3f} [{ci.lo:.3f}, {ci.hi:.3f}]" if ci is not None else "n/a"

    verb_row = (
        f"| 5 | Positive #2 — prefers-longer rate | {fmt(vb['verbosity_rate'])} | "
        "0.5 = no length bias; >0.5 = favors the longer answer on content-equal pairs |\n"
        if has_verbose else ""
    )
    verb_fig = "![verbosity bias](figures/verbosity_bias.png)\n" if has_verbose else ""

    md = f"""# Judge Trustworthiness Report

**Judge model:** `{model}`  |  **Bootstrap draws:** {B}  |  **Pairs:** {pos['n_pairs']}

Auditing the LLM-as-judge with paired synthetic controls — the
*"audit the auditor"* method, ported from fairness audits to LLM evaluation.

## Validation record

| # | Metric | Value (95% CI) | Reads as |
|---|--------|----------------|----------|
| 1 | Negative control — spurious decisive rate | {fmt(sdr)} | judge invents a winner on equivalent pairs this often (lower = better) |
| 2 | Negative control — content-side skew | {fmt(neg['side_skew'])} | P(picks ans1 \\| decisive); 0.5 = no systematic side preference |
| 3 | Positive #1 — first-position rate | {fmt(fpr)} | 0.5 = no primacy bias; >0.5 = favors the first-shown answer |
| 4 | Positive #1 — order-flip rate | {fmt(flip)} | verdict changes under a pure order swap this often |
{verb_row}| 6 | Discrimination (sanity) | {fmt(disc)} | picks the strong answer on strong-vs-weak pairs (should be high) |
| 7 | BH-FDR significant biases | {n_sig} of {len(fdr)} tests | tasks/dimensions flagged after multiplicity correction |

![negative control](figures/negative_control.png)
![position bias](figures/position_bias.png)
{verb_fig}
## FDR table (Benjamini–Hochberg, two-sided binomial vs the null)

{fdr.to_markdown(index=False, floatfmt='.3f') if len(fdr) else '(no tests)'}

## How to read this

- **Negative control (1–2)** = the paper's `Y_clean`: on pairs with no true quality
  difference, a calibrated judge should mostly tie with no systematic side preference.
  A high decisive rate or a side-skew CI excluding 0.5 means the judge *manufactures*
  preferences.
- **Positive controls (3–5)** inject *known* biases — presentation order and answer
  length. An unbiased judge is invariant to both: first-position rate ≈ 0.5, low flip
  rate, prefers-longer rate ≈ 0.5. A CI that excludes 0.5 is the audit *recovering a
  known bias*, exactly as `Y_inject` recovers a planted effect. The two axes are
  orthogonal (each pair is shown in both orders).
- **Discrimination (6)** guards against a degenerate "always tie" judge: it must still
  pick the better answer when one genuinely is better.
- **FDR (7)** controls false discoveries across the many per-task tests.

The verdict is a *distribution* (every line carries a bootstrap CI), not a single token.
"""
    report_path.write_text(md)
    print(f"wrote {report_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("verdicts", help="run_judge .jsonl dump OR an OpenCompass results dir")
    ap.add_argument("--model", default="(unknown)")
    ap.add_argument("--B", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--outdir", type=Path, default=ROOT / "outputs")
    args = ap.parse_args()

    verdicts = load_verdicts(args.verdicts)
    m = compute_metrics(verdicts, B=args.B, seed=args.seed)
    neg, pos, vb, disc, fdr, has_verbose = m["neg"], m["pos"], m["vb"], m["disc"], m["fdr"], m["has_verbose"]

    fig_dir = args.outdir / "figures"
    make_figures(neg, pos, vb, fig_dir)
    write_report(neg, pos, vb, disc, fdr, args.model, args.B,
                 args.outdir / "judge_trust_report.md", has_verbose)

    print("\n=== summary ===")
    print("neg spurious decisive:", neg["spurious_decisive_rate"])
    print("pos first-position   :", pos["first_position_rate"])
    print("pos flip rate        :", pos["flip_rate"])
    if has_verbose:
        print("len prefers-longer   :", vb["verbosity_rate"])
    print("discrimination       :", disc)
    print(f"FDR-significant: {int(fdr['sig_fdr'].sum())}/{len(fdr)}")


if __name__ == "__main__":
    main()
