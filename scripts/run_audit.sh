#!/usr/bin/env bash
# Full audit, end to end: build pairs -> judge them -> analyze -> report.
# Requires OC_JUDGE_* (and optionally OC_GEN_*) env vars. Source your .env first.
#
#   bash scripts/run_audit.sh            # ~40 questions (default)
#   N=20 bash scripts/run_audit.sh       # quick: 20 questions
#   OFFLINE=1 bash scripts/run_audit.sh  # no API: fabricated answers (plumbing test)
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_DIR"

N="${N:-}"
NARG=(); [ -n "$N" ] && NARG=(--n "$N")
MODEL="${OC_JUDGE_MODEL:-judge}"

if [ "${OFFLINE:-0}" = "1" ]; then
  echo "==> [1/3] build pairs (OFFLINE, fabricated answers)"
  python data/build_pairs.py "${NARG[@]}" --offline
  echo "==> OFFLINE mode: synthesize a (mildly biased) verdict stream — no judge calls"
  python - <<'PY'
import json, pathlib
import numpy as np
rng = np.random.default_rng(0)
rows = [json.loads(l) for l in open("data/pairs.jsonl")]
out = pathlib.Path("outputs/judge_raw"); out.mkdir(parents=True, exist_ok=True)
f = out / "verdicts_OFFLINE.jsonl"
P_FIRST, P_TIE, ACC, P_LONGER = 0.60, 0.45, 0.9, 0.65  # planted: mild primacy + length bias
def slot_for(order, winner):  # winner in {ans1, ans2}
    if order == "AB":
        return "first" if winner == "ans1" else "second"
    return "second" if winner == "ans1" else "first"
with f.open("w") as fh:
    for r in rows:
        o = r["order"]
        if r["pair_type"] == "null":
            slot = "tie" if rng.random() < P_TIE else ("first" if rng.random() < P_FIRST else "second")
        elif r["pair_type"] == "verbose":  # ans2 is the longer answer
            slot = "tie" if rng.random() < P_TIE else slot_for(o, "ans2" if rng.random() < P_LONGER else "ans1")
        else:  # nonnull: ans1 is the strong answer
            slot = slot_for(o, "ans1") if rng.random() < ACC else ("first" if rng.random() < 0.5 else "second")
        fh.write(json.dumps(dict(r, judge_raw=f"(offline) Verdict: {slot}", verdict_slot=slot)) + "\n")
print("wrote", f, len(rows), "rows")
PY
  DUMP="outputs/judge_raw/verdicts_OFFLINE.jsonl"
else
  : "${OC_JUDGE_API_KEY:?set OC_JUDGE_* first (cp .env.example .env; edit; source .env)}"
  echo "==> [1/3] build pairs (generate answers via OC_GEN_*/OC_JUDGE_*)"
  python data/build_pairs.py "${NARG[@]}"
  echo "==> [2/3] run judge"
  python src/run_judge.py
  DUMP="outputs/judge_raw/verdicts_${OC_JUDGE_MODEL//\//_}.jsonl"
fi

echo "==> [3/3] analyze + report"
python src/report.py "$DUMP" --model "$MODEL"

echo
echo "==> DONE."
echo "    report : outputs/judge_trust_report.md"
echo "    figures: outputs/figures/{negative_control,position_bias}.png"
