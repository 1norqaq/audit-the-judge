"""Stack several judges' validation records into one comparison.

Given N judge verdict dumps (each produced by run_judge over the SAME data/pairs.jsonl),
recompute every control axis per judge with the shared report.compute_metrics and emit:

    <outdir>/figures_compare/comparison.png   grouped bars across judges, per axis
    <outdir>/judge_comparison.md              one row per judge + how-to-read

Because all judges scored identical pairs, differences are the judge's, not the data's.

Usage:
    python src/compare_report.py docs/verdicts/verdicts_*.jsonl [--B 2000] [--outdir outputs]
    # or label each dump explicitly with name=path, e.g.
    #   python src/compare_report.py luna=outputs/judge_raw/verdicts_gpt-5.6-luna.jsonl ...
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from parse_outputs import load_verdicts  # noqa: E402
from report import compute_metrics  # noqa: E402

# Axes shown side by side. ref=0.5 axes have a "0.5 = unbiased" line; ref=None do not.
# lower_better flips the pass/flag reading for the two negative-control-style axes.
AXES = [
    ("spurious_decisive", "Neg: spurious-decisive\n(lower better)", 0.5, True),
    ("first_position", "Pos: first-position\n(0.5 = no primacy)", 0.5, False),
    ("prefers_longer", "Pos: prefers-longer\n(0.5 = no length bias)", 0.5, False),
    ("discrimination", "Sanity: discrimination\n(higher better)", None, False),
]


def _row_for(name: str, m: dict) -> dict:
    """Flatten one judge's metrics into the comparison row (CIs kept for plotting)."""
    vb_rate = m["vb"]["verbosity_rate"]
    fdr = m["fdr"]
    return {
        "judge": name,
        "n_pairs": m["pos"]["n_pairs"],
        "spurious_decisive": m["neg"]["spurious_decisive_rate"],
        "side_skew": m["neg"]["side_skew"],
        "first_position": m["pos"]["first_position_rate"],
        "flip": m["pos"]["flip_rate"],
        "prefers_longer": vb_rate,  # may be None if no verbose pairs were judged
        "discrimination": m["disc"],
        "n_sig": int(fdr["sig_fdr"].sum()) if len(fdr) else 0,
        "n_tests": len(fdr),
    }


def _excludes_half(ci) -> bool:
    return ci is not None and not (ci.lo <= 0.5 <= ci.hi)


def _verdict(axis: str, ci) -> str:
    """Emoji reading per axis, matching the single-judge report's language."""
    if ci is None:
        return "—"
    if axis == "spurious_decisive":
        return "⚠️ manufactures" if ci.point > 0.30 else "✅ mostly ties"
    if axis == "discrimination":
        return "✅ discriminates" if ci.lo > 0.7 else "⚠️ weak"
    if axis in ("first_position", "prefers_longer"):
        if not _excludes_half(ci):
            return "✅ unbiased"
        return "⚠️ favors " + ("first" if axis == "first_position" else "longer") + (
            "" if ci.point > 0.5 else " (reversed)"
        )
    return "—"


def make_figure(rows: list[dict], fig_dir: Path):
    fig_dir.mkdir(parents=True, exist_ok=True)
    names = [r["judge"] for r in rows]
    xs = range(len(names))
    fig, axes = plt.subplots(1, len(AXES), figsize=(4.2 * len(AXES), 4.0))
    palette = ["#4C72B0", "#55A868", "#8172B3", "#C44E52", "#CCB974", "#64B5CD"]
    for ax, (key, title, ref, _lower) in zip(axes, AXES):
        cis = [r[key] for r in rows]
        pts = [c.point if c is not None else 0.0 for c in cis]
        lo = [(c.point - c.lo) if c is not None else 0.0 for c in cis]
        hi = [(c.hi - c.point) if c is not None else 0.0 for c in cis]
        ax.bar(xs, pts, color=[palette[i % len(palette)] for i in xs], alpha=0.85)
        ax.errorbar(xs, pts, yerr=[lo, hi], fmt="none", ecolor="black", capsize=4, lw=1.2)
        if ref is not None:
            ax.axhline(ref, ls="--", color="#C44E52", lw=1.3)
        ax.set_xticks(list(xs))
        ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
        ax.set_title(title, fontsize=9)
        ax.set_ylim(0, 1)
    fig.suptitle("Judge comparison — paired synthetic controls (95% CI)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(fig_dir / "comparison.png", dpi=140)
    plt.close(fig)


def write_report(rows: list[dict], B: int, report_path: Path):
    def fmt(ci) -> str:
        return f"{ci.point:.3f} [{ci.lo:.3f}, {ci.hi:.3f}]" if ci is not None else "n/a"

    header = (
        "| Judge | Pairs | Neg: spurious-decisive | Neg: side-skew | Pos: first-position | "
        "Pos: prefers-longer | Discrimination | FDR-sig |\n"
        "|---|---|---|---|---|---|---|---|\n"
    )
    body = ""
    for r in rows:
        body += (
            f"| `{r['judge']}` | {r['n_pairs']} | {fmt(r['spurious_decisive'])} {_verdict('spurious_decisive', r['spurious_decisive'])} | "
            f"{fmt(r['side_skew'])} | {fmt(r['first_position'])} {_verdict('first_position', r['first_position'])} | "
            f"{fmt(r['prefers_longer'])} {_verdict('prefers_longer', r['prefers_longer'])} | "
            f"{fmt(r['discrimination'])} {_verdict('discrimination', r['discrimination'])} | "
            f"{r['n_sig']}/{r['n_tests']} |\n"
        )

    md = f"""# Judge Comparison Report

**Judges:** {len(rows)}  |  **Bootstrap draws:** {B}  |  every judge scored the **same** `data/pairs.jsonl`

Each judge is audited with the same paired synthetic controls as the single-judge report
(*"audit the auditor"*, ported to LLM-as-judge). Because the answer pairs are identical
across judges, every difference below is a property of the **judge**, not the data.

## Comparison record

{header}{body}
![judge comparison](figures_compare/comparison.png)

## How to read this

- **Neg: spurious-decisive** — on equivalent pairs (no true quality gap), how often the
  judge invents a winner. Lower is better; a calibrated judge mostly ties.
- **Neg: side-skew** — among decisive null verdicts, P(picks answer-1). 0.5 = no
  content-side preference (a CI excluding 0.5 is a systematic side bias).
- **Pos: first-position** — primacy bias. 0.5 = order-invariant; >0.5 favors whichever
  answer is shown first. A CI excluding 0.5 is the control *recovering* a real bias.
- **Pos: prefers-longer** — length bias on concise-vs-detailed content-equal pairs.
  0.5 = no length preference; >0.5 favors the longer answer.
- **Discrimination** — sanity check: picks the strong answer on strong-vs-weak pairs.
  Should be high; guards against a degenerate "always tie" judge.
- **FDR-sig** — per-task × per-axis biases surviving Benjamini–Hochberg correction.

Each cell carries a bootstrap 95% CI (cluster-bootstrap over pairs): the verdict is a
*distribution*, not a single token. A judge to trust as a leaderboard backbone ties the
nulls, sits near 0.5 on both positive axes, and discriminates quality reliably.
"""
    report_path.write_text(md)
    print(f"wrote {report_path}")


def parse_specs(items: list[str]) -> list[tuple[str, Path]]:
    """Each item is 'name=path' (or bare 'path', name inferred from filename)."""
    out = []
    for it in items:
        if "=" in it:
            name, path = it.split("=", 1)
        else:
            path = it
            name = Path(it).stem.replace("verdicts_", "")
        out.append((name, Path(path)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dumps", nargs="+", help="name=verdicts.jsonl for each judge (name optional)")
    ap.add_argument("--B", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--outdir", type=Path, default=ROOT / "outputs")
    args = ap.parse_args()

    rows = []
    for name, path in parse_specs(args.dumps):
        if not path.exists():
            print(f"  ! skipping {name}: {path} not found", file=sys.stderr)
            continue
        verdicts = load_verdicts(path)
        m = compute_metrics(verdicts, B=args.B, seed=args.seed)
        rows.append(_row_for(name, m))
        print(f"  computed {name}: {len(verdicts)} verdicts", file=sys.stderr)

    if not rows:
        sys.exit("no usable verdict dumps")

    make_figure(rows, args.outdir / "figures_compare")
    write_report(rows, args.B, args.outdir / "judge_comparison.md")

    print("\n=== comparison ===")
    for r in rows:
        print(f"{r['judge']:16s} decisive={r['spurious_decisive'].point:.3f}  "
              f"first-pos={r['first_position'].point:.3f}  "
              f"longer={r['prefers_longer'].point if r['prefers_longer'] else float('nan'):.3f}  "
              f"disc={r['discrimination'].point:.3f}  FDR={r['n_sig']}/{r['n_tests']}")


if __name__ == "__main__":
    main()
