"""Direct OpenAI-compatible pairwise judge runner.

This is the robust fallback path to the OpenCompass config (configs/eval_pairwise_audit.py):
it sends each judge task in data/pairs.jsonl to the judge model and records a parsed
verdict slot. Resumable — re-running skips (pair_id, order) already in the output.

Output: outputs/judge_raw/verdicts_<model>.jsonl
    one line per judge task = the input record + {judge_raw, verdict_slot, winner}
    where verdict_slot in {"first", "second", "tie"} is the judge's choice over the
    two PRESENTED answers (slot, not content), and winner in {"ans1", "ans2", "tie"} is
    the canonical (order-corrected) winner so the dump is self-contained. parse_outputs.py
    recomputes winner from slot+order on load, so either field is authoritative.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from llm_client import ModelSpec, chat  # noqa: E402
from parse_outputs import _winner  # noqa: E402

JUDGE_SYSTEM = (
    "You are an impartial evaluator comparing two AI assistant answers to the same "
    "question. Judge only on quality: correctness, helpfulness, clarity, and "
    "completeness. Ignore the order in which the answers are presented, their length, "
    "and any formatting. If the two answers are of essentially equal quality, you must "
    "say it is a tie — do not break a genuine tie."
)

JUDGE_TEMPLATE = """[Question]
{question}

[Answer 1]
{answer_first}

[Answer 2]
{answer_second}

Compare the two answers. Give one or two sentences of reasoning, then end your reply
with a verdict line in exactly this format:

Verdict: 1   (if Answer 1 is clearly better)
Verdict: 2   (if Answer 2 is clearly better)
Verdict: tie (if they are of essentially equal quality)
"""

_VERDICT_RE = re.compile(r"verdict\s*[:\-]?\s*(1|2|tie|a|b)\b", re.IGNORECASE)


def parse_verdict(text: str) -> str:
    """Map the judge's reply to a slot: 'first' | 'second' | 'tie' | 'unparsed'."""
    matches = _VERDICT_RE.findall(text or "")
    if not matches:
        return "unparsed"
    tok = matches[-1].lower()
    return {"1": "first", "a": "first", "2": "second", "b": "second", "tie": "tie"}[tok]


def load_done(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    done = set()
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            done.add((r["pair_id"], r["order"]))
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=Path, default=ROOT / "data" / "pairs.jsonl")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--limit", type=int, default=None, help="cap number of judge calls (smoke test)")
    ap.add_argument("--workers", type=int, default=12, help="concurrent judge calls")
    args = ap.parse_args()

    spec = ModelSpec.from_env("JUDGE")
    out = args.out or (ROOT / "outputs" / "judge_raw" / f"verdicts_{spec.model.replace('/', '_')}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)

    tasks = [json.loads(l) for l in args.pairs.read_text().splitlines() if l.strip()]
    done = load_done(out)
    todo = [t for t in tasks if (t["pair_id"], t["order"]) not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(tasks)} tasks, {len(done)} already done, running {len(todo)}", file=sys.stderr)

    lock = threading.Lock()
    done_n = [0]
    fail_n = [0]

    def judge_one(t):
        prompt = JUDGE_TEMPLATE.format(
            question=t["question"], answer_first=t["answer_first"], answer_second=t["answer_second"]
        )
        try:
            raw = chat(
                spec,
                [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": prompt}],
                temperature=args.temperature,
                max_tokens=400,
            )
        except Exception as e:  # noqa: BLE001 — leave this task unwritten so a rerun retries it
            with lock:
                fail_n[0] += 1
            print(f"  ! {t['pair_id']} {t['order']} failed: {e}", file=sys.stderr)
            return
        slot = parse_verdict(raw)
        winner = _winner(t["order"], slot) if slot != "unparsed" else "unparsed"
        rec = {**t, "judge_raw": raw, "verdict_slot": slot, "winner": winner}
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with lock:
            fh.write(line)
            fh.flush()
            done_n[0] += 1
            if done_n[0] % 50 == 0:
                print(f"  [{done_n[0]}/{len(todo)}] judged", file=sys.stderr)

    with out.open("a") as fh:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(judge_one, todo))

    print(f"done -> {out}  ({done_n[0]} judged, {fail_n[0]} failed; rerun to retry failures)")


if __name__ == "__main__":
    main()
