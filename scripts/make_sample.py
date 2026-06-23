"""Render the committed SAMPLE report + figures under docs/sample/.

Fully reproducible and API-free: it synthesizes a verdict stream from a judge with
*planted* biases (mild primacy + a clear length bias), then runs the real analysis.
The figures in the README come from here so a visitor sees the output shape without
needing a key. Re-run:  python scripts/make_sample.py

The numbers are SYNTHETIC by construction — a real audit replaces this with
scripts/run_audit.sh against an actual judge.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_audit import synth_verdicts  # reuse the planted-bias generator

OUT = ROOT / "docs" / "sample"
OUT.mkdir(parents=True, exist_ok=True)

# A judge with a mild primacy bias and a clear length bias, otherwise calibrated.
v = synth_verdicts(n_pairs=160, p_first=0.62, p_tie_null=0.50,
                   acc_nonnull=0.90, p_longer=0.71, p_tie_verbose=0.45, seed=42)

cols = ["pair_id", "task", "pair_type", "true_label", "order", "verdict_slot"]
dump = OUT / "sample_verdicts.jsonl"
dump.write_text("".join(json.dumps({c: r[c] for c in cols}) + "\n" for _, r in v.iterrows()))
print("wrote", dump, len(v), "rows")

subprocess.run(
    [sys.executable, str(ROOT / "src" / "report.py"), str(dump),
     "--model", "SYNTHETIC DEMO judge (planted: 0.62 primacy, 0.71 length bias)",
     "--B", "2000", "--outdir", str(OUT)],
    check=True,
)
print("sample written under", OUT)
