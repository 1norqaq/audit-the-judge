"""Audit several judges over the SAME pairs and produce one comparison.

End to end:
  1. build data/pairs.jsonl ONCE with the fixed GENERATOR (skipped if it already
     exists, unless --rebuild-pairs) so every judge scores identical answers;
  2. run each judge in configs/models.py over those pairs (resumable per judge);
  3. write a per-judge report + the combined judge_comparison.md.

Keys come from .env (referenced by env-var NAME in configs/models.py). A judge whose
key is unset is skipped with a warning, so you can compare whatever subset you have keys
for. Everything is resumable: re-run to add a judge or retry failed calls.

    python src/run_compare.py                       # all judges with keys present
    python src/run_compare.py --only gpt-5.6-luna kimi-k2.6   # a subset
    python src/run_compare.py --n 40                # 40 questions (cheaper smoke)
    python src/run_compare.py --rebuild-pairs       # regenerate the answer pairs
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from parse_outputs import load_verdicts  # noqa: E402
from registry import load_env_file, load_registry, spec_from_entry  # noqa: E402
from run_judge import run_judge  # noqa: E402

import compare_report  # noqa: E402
import report  # noqa: E402

PAIRS = ROOT / "data" / "pairs.jsonl"
RAW_DIR = ROOT / "outputs" / "judge_raw"


def build_pairs(generator: dict, n: int | None, rebuild: bool) -> None:
    if PAIRS.exists() and not rebuild:
        print(f"==> pairs exist ({PAIRS}); reusing. Use --rebuild-pairs to regenerate.")
        return
    gspec = spec_from_entry(generator)
    if gspec is None:
        sys.exit(f"generator key {generator['api_key_env']} not set — cannot build pairs.")
    print(f"==> building pairs with generator '{generator['name']}' ({gspec.model})")
    env = {**os.environ, "OC_GEN_MODEL": gspec.model, "OC_GEN_API_KEY": gspec.api_key,
           "OC_GEN_API_BASE": gspec.api_base}
    cmd = [sys.executable, str(ROOT / "data" / "build_pairs.py")]
    if n:
        cmd += ["--n", str(n)]
    subprocess.run(cmd, env=env, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", default=None, help="judge names to run (default: all with keys)")
    ap.add_argument("--n", type=int, default=None, help="number of seed questions (fewer = cheaper)")
    ap.add_argument("--limit", type=int, default=None, help="cap judge calls per model (smoke)")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--temperature", type=float, default=0.0, help="default judge temperature")
    ap.add_argument("--B", type=int, default=2000, help="bootstrap draws for the reports")
    ap.add_argument("--rebuild-pairs", action="store_true")
    ap.add_argument("--skip-per-model-reports", action="store_true")
    args = ap.parse_args()

    load_env_file()
    reg = load_registry()
    generator, judges = reg.GENERATOR, reg.JUDGES
    if args.only:
        judges = [j for j in judges if j["name"] in set(args.only)]
        if not judges:
            sys.exit(f"--only {args.only} matched no judge in configs/models.py")

    build_pairs(generator, args.n, args.rebuild_pairs)

    to_run = []
    for entry in judges:
        spec = spec_from_entry(entry)
        if spec is None:
            print(f"==> skip '{entry['name']}': {entry['api_key_env']} not set", file=sys.stderr)
            continue
        to_run.append((entry, spec))

    def judge_model(item):
        # Judges hit independent providers, so run them concurrently: wall-clock becomes the
        # slowest single judge, not the sum. Each run_judge keeps its own worker pool + output
        # file, so `--workers` is the per-provider concurrency (5 providers x workers total).
        entry, spec = item
        out = RAW_DIR / f"verdicts_{entry['name']}.jsonl"
        print(f"==> judge '{entry['name']}' ({spec.model}) -> {out.name}", file=sys.stderr)
        run_judge(spec, PAIRS, out,
                  temperature=entry.get("temperature", args.temperature),
                  max_tokens=entry.get("max_tokens", 400),
                  token_param=entry.get("token_param", "max_tokens"),
                  extra_body=entry.get("extra_body"),
                  limit=args.limit, workers=args.workers)
        return (entry["name"], out)

    done_dumps: list[tuple[str, Path]] = []
    if to_run:
        with ThreadPoolExecutor(max_workers=len(to_run)) as ex:
            done_dumps = list(ex.map(judge_model, to_run))

    if not done_dumps:
        sys.exit("no judges ran (no API keys set?). Fill .env — see .env.example.")

    if not args.skip_per_model_reports:
        for name, dump in done_dumps:
            outdir = ROOT / "outputs" / "reports" / name
            verdicts = load_verdicts(dump)
            m = report.compute_metrics(verdicts, B=args.B, seed=0)
            report.make_figures(m["neg"], m["pos"], m["vb"], outdir / "figures")
            report.write_report(m["neg"], m["pos"], m["vb"], m["disc"], m["fdr"], name, args.B,
                                 outdir / "judge_trust_report.md", m["has_verbose"])

    rows = []
    for name, dump in done_dumps:
        m = report.compute_metrics(load_verdicts(dump), B=args.B, seed=0)
        rows.append(compare_report._row_for(name, m))
    compare_report.make_figure(rows, ROOT / "outputs" / "figures_compare")
    compare_report.write_report(rows, args.B, ROOT / "outputs" / "judge_comparison.md")

    print("\n==> DONE.")
    print(f"    comparison : outputs/judge_comparison.md")
    print(f"    figure     : outputs/figures_compare/comparison.png")
    if not args.skip_per_model_reports:
        print(f"    per-judge  : outputs/reports/<judge>/judge_trust_report.md")


if __name__ == "__main__":
    main()
