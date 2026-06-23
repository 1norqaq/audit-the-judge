#!/usr/bin/env bash
# Day 0: environment. Idempotent — safe to re-run.
# Installs Miniconda if `conda` is absent, creates the `oc` env (py3.10),
# clones OpenCompass, and installs it + this project's requirements.
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OC_DIR="${OC_DIR:-$HOME/projects/opencompass}"
MINICONDA_DIR="${MINICONDA_DIR:-$HOME/miniconda3}"
ENV_NAME="${ENV_NAME:-oc}"

echo "==> project: $PROJ_DIR"
echo "==> opencompass: $OC_DIR"

# 1. conda (install Miniconda if missing)
if ! command -v conda >/dev/null 2>&1; then
  if [ ! -x "$MINICONDA_DIR/bin/conda" ]; then
    echo "==> conda not found; installing Miniconda to $MINICONDA_DIR"
    arch="$(uname -m)"
    case "$arch" in
      x86_64)  mc="Miniconda3-latest-Linux-x86_64.sh" ;;
      aarch64) mc="Miniconda3-latest-Linux-aarch64.sh" ;;
      *) echo "unsupported arch: $arch" >&2; exit 1 ;;
    esac
    curl -fsSL "https://repo.anaconda.com/miniconda/$mc" -o /tmp/miniconda.sh
    bash /tmp/miniconda.sh -b -p "$MINICONDA_DIR"
    rm -f /tmp/miniconda.sh
  fi
  export PATH="$MINICONDA_DIR/bin:$PATH"
fi
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"

# 2. env
# Accept Anaconda channel ToS non-interactively (no-op once accepted); harmless on
# conda builds that lack the `tos` subcommand.
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >/dev/null 2>&1 || true
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r    >/dev/null 2>&1 || true
if ! conda env list | grep -qE "^${ENV_NAME}\s"; then
  echo "==> creating conda env '$ENV_NAME' (python 3.10)"
  conda create -y -n "$ENV_NAME" python=3.10
fi
conda activate "$ENV_NAME"
echo "==> python: $(python --version)"

# 3. OpenCompass
if [ ! -d "$OC_DIR/.git" ]; then
  echo "==> cloning OpenCompass to $OC_DIR"
  git clone --depth 1 https://github.com/open-compass/opencompass "$OC_DIR"
fi
echo "==> pip install -e opencompass (this is the slow step)"
pip install -e "$OC_DIR"

# 4. this project's analysis deps
pip install -r "$PROJ_DIR/requirements.txt"

# 5. sanity
python - <<'PY'
import opencompass, numpy, pandas, scipy, statsmodels, matplotlib, openai
print("OK imports: opencompass", opencompass.__version__ if hasattr(opencompass,'__version__') else '(ver n/a)')
PY

echo
echo "==> DONE. Activate with:  conda activate $ENV_NAME"
echo "==> Then:  cp $PROJ_DIR/.env.example $PROJ_DIR/.env  && edit it  && source $PROJ_DIR/.env"
