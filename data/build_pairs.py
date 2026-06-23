"""Build the paired-comparison dataset for the judge audit.

For each seed question we construct two *canonical* answers (ans1, ans2) and a
known ground-truth label, then emit the pair in BOTH presentation orders so the
same judge run yields both controls:

  * NULL pair (negative control): ans1, ans2 are two temperature>0 samples of the
    SAME model on the SAME question -> truly equivalent, true_label="tie".
    A calibrated judge should not invent a decisive preference.

  * NONNULL pair (sanity / discrimination): ans1 = a strong answer, ans2 = a
    deliberately weak answer (terse, low-effort) -> true_label="ans1".
    Confirms the judge can actually discriminate quality (it isn't just random).

  * VERBOSE pair (positive control, length axis): ans1 = a CONCISE answer, ans2 = a
    DETAILED answer to the SAME question, BOTH asked to be correct and complete and
    differing only in how thoroughly they explain -> true_label="tie". The metric is
    P(judge picks ans2 = the longer answer); 0.5 = no length bias.
    NOTE: ans2 is a separately generated thorough answer, NOT ans1 + filler. An
    "ans1 + boilerplate" construction is a literal superset with obvious padding,
    which a competent judge correctly rejects every time -> a degenerate 0.0 rate
    that is a pipeline artifact, not a length-bias measurement. (See README fix log.)

Each pair is written twice:
    order="AB": first_slot=ans1, second_slot=ans2
    order="BA": first_slot=ans2, second_slot=ans1
so flip rate and first-position win rate fall out of the parsed verdicts.

Modes:
    (default) call the generator model via OC_GEN_* (or OC_JUDGE_*) env vars.
    --offline  fabricate answers locally (no API key) so the pipeline can be exercised.
    --only T [T ...]  emit only these pair types (e.g. `--only verbose` to cheaply
                      regenerate just the length-axis pairs); default all three.

Output: data/pairs.jsonl  (one judge task per line)
Schema per line:
    pair_id, task, pair_type ("null"|"nonnull"|"verbose"), true_label ("tie"|"ans1"|"ans2"),
    order ("AB"|"BA"), question, answer_first, answer_second
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

QUESTIONS = HERE / "questions.jsonl"
OUT = HERE / "pairs.jsonl"
PAIR_TYPES = ["null", "nonnull", "verbose"]

WEAK_SUFFIX = (
    "\n\nAnswer in a single short, low-effort sentence. Do not elaborate, "
    "give no examples, and skip any caveats."
)
# Length axis: two genuinely content-equivalent answers that differ only in verbosity.
CONCISE_SUFFIX = "\n\nAnswer correctly and completely, but concisely — at most 2-3 sentences, no filler."
DETAILED_SUFFIX = (
    "\n\nAnswer correctly and completely, explaining thoroughly with full detail, "
    "context, and a brief example."
)


def load_questions(n: int | None) -> list[dict]:
    rows = [json.loads(l) for l in QUESTIONS.read_text().splitlines() if l.strip()]
    return rows[:n] if n else rows


def gen_api(spec, q: str, temperature: float, need: set[str]) -> dict:
    """Generate only the answers required by the selected pair types."""
    from llm_client import chat

    out: dict = {}
    if "null" in need:  # two independent samples -> equivalent
        out["a1"] = chat(spec, [{"role": "user", "content": q}], temperature=temperature)
        out["a2"] = chat(spec, [{"role": "user", "content": q}], temperature=temperature)
    if "nonnull" in need:  # strong vs deliberately weak
        out["strong"] = chat(spec, [{"role": "user", "content": q}], temperature=0.0)
        out["weak"] = chat(spec, [{"role": "user", "content": q + WEAK_SUFFIX}], temperature=temperature, max_tokens=120)
    if "verbose" in need:  # concise vs detailed, both correct+complete
        out["concise"] = chat(spec, [{"role": "user", "content": q + CONCISE_SUFFIX}], temperature=0.0)
        out["detailed"] = chat(spec, [{"role": "user", "content": q + DETAILED_SUFFIX}], temperature=0.0, max_tokens=1024)
    return out


def gen_offline(q: str, need: set[str]) -> dict:
    """Deterministic placeholder answers, no API."""
    core = (
        f"On '{q[:60]}': the key point is to be correct, clear, and complete, "
        "laying out the reasoning in order and ending with a concrete takeaway"
    )
    out: dict = {}
    if "null" in need:
        out["a1"] = core + "."
        out["a2"] = core.replace("key point is", "main thing is") + "."
    if "nonnull" in need:
        out["strong"] = core + ", grounding each claim with a brief example."
        out["weak"] = "It depends."
    if "verbose" in need:  # content-equivalent, naturally different lengths
        out["concise"] = core + "."
        out["detailed"] = (
            core + ". In more detail, each step follows from the previous one, and a short "
            "worked example makes the idea concrete; the same conclusion holds throughout."
        )
    return out


def emit_pair(records, pair_id, task, pair_type, true_label, question, ans1, ans2):
    for order, (first, second) in (("AB", (ans1, ans2)), ("BA", (ans2, ans1))):
        records.append(
            {
                "pair_id": pair_id,
                "task": task,
                "pair_type": pair_type,
                "true_label": true_label,
                "order": order,
                "question": question,
                "answer_first": first,
                "answer_second": second,
            }
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None, help="number of seed questions to use")
    ap.add_argument("--temperature", type=float, default=0.7, help="sampling temp for null-pair resamples")
    ap.add_argument("--offline", action="store_true", help="fabricate answers locally (no API key)")
    ap.add_argument("--only", nargs="+", choices=PAIR_TYPES, default=PAIR_TYPES,
                    help="emit only these pair types (default: all)")
    ap.add_argument("--workers", type=int, default=12, help="concurrent answer-generation questions")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    need = set(args.only)
    questions = load_questions(args.n)
    spec = None
    if not args.offline:
        from llm_client import ModelSpec

        spec = ModelSpec.from_env("GEN")

    def process(i_row):
        i, row = i_row
        q, task = row["question"], row.get("task", "general")
        a = gen_offline(q, need) if args.offline else gen_api(spec, q, args.temperature, need)
        recs: list[dict] = []
        if "null" in need:
            emit_pair(recs, f"{row['id']}::null", task, "null", "tie", q, a["a1"], a["a2"])
        if "nonnull" in need:
            emit_pair(recs, f"{row['id']}::nonnull", task, "nonnull", "ans1", q, a["strong"], a["weak"])
        if "verbose" in need:
            # ans1 = concise, ans2 = detailed; content-equivalent, ans2 is the LONGER one.
            emit_pair(recs, f"{row['id']}::verbose", task, "verbose", "tie", q, a["concise"], a["detailed"])
        print(f"[{i+1}/{len(questions)}] {row['id']}", file=sys.stderr)
        return i, recs

    workers = 1 if args.offline else args.workers
    by_index: dict[int, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, recs in ex.map(process, list(enumerate(questions))):
            by_index[i] = recs
    records = [r for i in range(len(questions)) for r in by_index[i]]  # stable order

    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    print(f"wrote {len(records)} judge tasks ({len(questions)} questions x {len(need)} pair-types x 2 orders) -> {args.out}")


if __name__ == "__main__":
    main()
