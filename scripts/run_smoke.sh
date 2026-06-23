#!/usr/bin/env bash
# Day 1-2: run one LLM-judge eval through OpenCompass and confirm the outputs appear.
# Requires OC_JUDGE_* env vars (source your .env first).
set -euo pipefail

OC_DIR="${OC_DIR:-$HOME/projects/opencompass}"
PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${OC_JUDGE_API_KEY:?set OC_JUDGE_* first (cp .env.example .env; edit; source .env)}"

cd "$OC_DIR"
python run.py "$PROJ_DIR/configs/eval_judge_min.py"

echo
echo "==> look for outputs under: $OC_DIR/outputs/judge_min/<timestamp>/"
echo "    summary/*.csv      (the report)"
echo "    results/**/*.json  (one record per judgment)"
ls -dt "$OC_DIR"/outputs/judge_min/*/ 2>/dev/null | head -1
