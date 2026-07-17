#!/usr/bin/env bash
# Compare several LLM judges over one shared set of pairs.
# Fill .env with the API keys named in configs/models.py, then:
#
#   bash scripts/run_compare.sh                 # all judges that have a key set
#   N=40 bash scripts/run_compare.sh            # 40 questions (cheaper)
#   ONLY="gpt-5.6-luna kimi-k2.6" bash scripts/run_compare.sh   # a subset
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_DIR"

[ -f .env ] && source .env

ARGS=()
[ -n "${N:-}" ]    && ARGS+=(--n "$N")
[ -n "${ONLY:-}" ] && ARGS+=(--only $ONLY)

python src/run_compare.py "${ARGS[@]}"

echo
echo "==> DONE."
echo "    comparison : outputs/judge_comparison.md"
echo "    figure     : outputs/figures_compare/comparison.png"
echo "    per-judge  : outputs/reports/<judge>/judge_trust_report.md"
