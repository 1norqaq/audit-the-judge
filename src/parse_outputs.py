"""Normalize judge outputs into one tidy verdict table.

Reads either:
  * a direct run_judge.py dump (outputs/judge_raw/verdicts_*.jsonl), or
  * an OpenCompass subjective results dir (results/*.json) -- best-effort.

and returns a DataFrame with one canonical schema that every analysis module
consumes:

    pair_id, task, pair_type, true_label, order,
    verdict_slot   in {first, second, tie, unparsed}   (judge's choice over slots)
    winner         in {ans1, ans2, tie, unparsed}       (canonical, order-corrected)

Slot -> canonical winner mapping:
    order "AB": first_slot = ans1  -> first->ans1, second->ans2
    order "BA": first_slot = ans2  -> first->ans2, second->ans1
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

_SLOT_TO_WINNER = {
    "AB": {"first": "ans1", "second": "ans2", "tie": "tie", "unparsed": "unparsed"},
    "BA": {"first": "ans2", "second": "ans1", "tie": "tie", "unparsed": "unparsed"},
}


def _winner(order: str, slot: str) -> str:
    return _SLOT_TO_WINNER[order][slot]


def load_run_judge_dump(path: str | Path) -> pd.DataFrame:
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    df = pd.DataFrame(rows)
    keep = ["pair_id", "task", "pair_type", "true_label", "order", "verdict_slot"]
    df = df[keep].copy()
    df["winner"] = [_winner(o, s) for o, s in zip(df["order"], df["verdict_slot"])]
    return df


def load_opencompass_results(results_dir: str | Path) -> pd.DataFrame:
    """Best-effort loader for OpenCompass subjective results JSON.

    OC writes one JSON per (model, dataset) under results/<model>/<dataset>.json,
    keyed by example index, each value carrying the prediction/gold/origin_prompt.
    Field names vary across OC versions, so we read defensively and keep only what
    maps cleanly onto our schema (pair_id/order/pair_type/true_label must have been
    threaded through the dataset's metadata). If your OC config differs, prefer the
    run_judge dump; this exists so the analysis CAN consume OC output, not to lock you in.
    """
    rows = []
    for jf in Path(results_dir).rglob("*.json"):
        try:
            blob = json.loads(jf.read_text())
        except json.JSONDecodeError:
            continue
        items = blob.get("details", blob) if isinstance(blob, dict) else {}
        if not isinstance(items, dict):
            continue
        for _, ex in items.items():
            if not isinstance(ex, dict):
                continue
            meta = {**ex, **ex.get("gold", {})} if isinstance(ex.get("gold"), dict) else ex
            slot = _slot_from_oc(ex)
            order = meta.get("order")
            if order not in ("AB", "BA") or slot is None:
                continue
            rows.append(
                {
                    "pair_id": meta.get("pair_id"),
                    "task": meta.get("task", "general"),
                    "pair_type": meta.get("pair_type"),
                    "true_label": meta.get("true_label"),
                    "order": order,
                    "verdict_slot": slot,
                    "winner": _winner(order, slot),
                }
            )
    if not rows:
        raise ValueError(
            f"No usable rows parsed from {results_dir}. OC layout varies by version — "
            "use the run_judge.py dump path instead (see README)."
        )
    return pd.DataFrame(rows)


def _slot_from_oc(ex: dict) -> str | None:
    """Pull a verdict slot from an OC example dict, trying common field names."""
    import re

    for key in ("prediction", "pred", "judge", "response", "output"):
        val = ex.get(key)
        if isinstance(val, str) and val:
            m = re.findall(r"(1|2|tie|A|B)", val)
            if m:
                tok = m[-1].lower()
                return {"1": "first", "a": "first", "2": "second", "b": "second", "tie": "tie"}.get(tok)
    return None


def load_verdicts(path: str | Path) -> pd.DataFrame:
    """Dispatch on path: a .jsonl file -> run_judge dump; a directory -> OC results."""
    p = Path(path)
    df = load_opencompass_results(p) if p.is_dir() else load_run_judge_dump(p)
    # drop unparsed verdicts but report how many
    n_bad = int((df["verdict_slot"] == "unparsed").sum())
    if n_bad:
        print(f"[parse_outputs] dropping {n_bad}/{len(df)} unparsed verdicts")
    return df[df["verdict_slot"] != "unparsed"].reset_index(drop=True)


if __name__ == "__main__":
    import sys

    df = load_verdicts(sys.argv[1])
    print(df.head(12).to_string())
    print(f"\n{len(df)} verdicts | pair_types: {df['pair_type'].value_counts().to_dict()}")
