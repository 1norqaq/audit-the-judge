"""Shared loader for the model registry (configs/models.py) and .env.

One source of truth for the multi-model setup, used by:
  * make_questions.py  -> QUESTION_GENERATOR  (writes the seed question bank)
  * run_compare.py     -> GENERATOR (answer pairs) + JUDGES (audited)

Keys are referenced by env-var NAME in configs/models.py and read from the process
environment (fill .env; see .env.example). spec_from_entry returns None when a key is
unset so callers can skip or fail with a clear message.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from llm_client import ModelSpec

ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path | None = None) -> None:
    """Minimal .env loader: `export KEY=VALUE` / `KEY=VALUE`; never overrides a set var."""
    path = path or (ROOT / ".env")
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line[len("export "):].strip() if line.startswith("export ") else line
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def load_registry():
    """Import configs/models.py as a module (it is config, not on the import path)."""
    spec = importlib.util.spec_from_file_location("models_cfg", ROOT / "configs" / "models.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def spec_from_entry(entry: dict) -> ModelSpec | None:
    """Build a ModelSpec from a registry entry, reading its key from the named env var.

    Returns None if that key is unset (caller decides: skip the judge, or fail).
    """
    key = os.getenv(entry["api_key_env"])
    if not key:
        return None
    return ModelSpec(model=entry["model"], api_key=key, api_base=entry["api_base"])
