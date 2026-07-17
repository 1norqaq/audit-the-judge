"""Expand data/questions.jsonl to a larger, diverse bank using the QUESTION_GENERATOR.

Keeps the curated seed questions, then asks the model for more per task category,
dedupes, and writes them back. Reproducible enough for an audit: questions are
generic and self-contained; the audit's validity does not depend on which exact
questions are used, only that they are diverse and answerable.

The question generator is the QUESTION_GENERATOR in configs/models.py — a strong,
neutral third-party model (Claude Opus 4.8 by default), deliberately decoupled from the
answer generator and the judges so the questions are not authored by anything under
audit. Its API key comes from that entry's env var (ANTHROPIC_API_KEY by default).

Generation is balanced per category: each category is filled to --per-cat via repeated
generator calls (deduping, telling the model what it already has), so no category is
truncated. --fresh ignores the existing bank and builds it entirely from the generator.

Run (needs the QUESTION_GENERATOR key in .env):
    python data/make_questions.py --per-cat 100 --fresh          # 100 x 5 = 500, all Opus
    python data/make_questions.py --per-cat 5 --fresh --out /tmp/preview.jsonl   # cheap sample
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from llm_client import chat  # noqa: E402
from registry import load_env_file, load_registry, spec_from_entry  # noqa: E402

QFILE = HERE / "questions.jsonl"

CATEGORIES = {
    "kn": ("knowledge", "general-knowledge / explain-a-concept questions (science, everyday phenomena, economics, history)"),
    "rs": ("reasoning", "reasoning / logic / word-problem questions answerable by thinking, no external data"),
    "wr": ("writing", "short writing tasks (notes, summaries, rewrites, small creative prompts)"),
    "cd": ("coding", "programming questions (small functions, language concepts, simple SQL)"),
    "ad": ("advice", "practical everyday advice questions"),
}


def _parse_list(text: str) -> list[str]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        arr = json.loads(text[text.index("[") : text.rindex("]") + 1])
        return [str(x).strip() for x in arr if str(x).strip()]
    except Exception:
        # fallback: one question per line, strip numbering/bullets
        out = []
        for line in text.splitlines():
            s = re.sub(r"^\s*(?:\d+[.)]|[-*])\s*", "", line).strip().strip('"')
            if len(s) > 8 and s.endswith(("?", ".")):
                out.append(s)
        return out


def gen_category(spec, desc, n, *, avoid=None, temperature=None, max_tokens=2000) -> list[str]:
    """Ask the generator for n questions in a category. `avoid` is a list of
    already-collected questions the model is told not to repeat (diversity across rounds)."""
    avoid_txt = ""
    if avoid:
        recent = "\n".join(f"- {q}" for q in avoid[-20:])
        avoid_txt = (
            "\n\nDo NOT repeat or lightly rephrase any of these already-collected questions:\n"
            + recent
        )
    prompt = (
        f"Generate {n} diverse, self-contained {desc}. "
        "Each must be a single question or instruction answerable in a few sentences "
        "with no external context, files, or images. Keep them varied and non-redundant. "
        'Return ONLY a JSON array of strings, e.g. ["...", "..."].' + avoid_txt
    )
    raw = chat(spec, [{"role": "user", "content": prompt}], temperature=temperature, max_tokens=max_tokens)
    return _parse_list(raw)


def build_category(spec, task, desc, per_cat, seed_qs, *, temperature, batch, max_rounds):
    """Fill one category up to `per_cat` unique questions: keep the seeds, then loop the
    generator (deduping) until the target is reached or the round budget runs out."""
    result = list(dict.fromkeys(q.strip() for q in seed_qs if q.strip()))[:per_cat]
    seen = {q.lower() for q in result}
    rounds = 0
    while len(result) < per_cat and rounds < max_rounds:
        rounds += 1
        need = per_cat - len(result)
        batch_qs = gen_category(spec, desc, min(batch, need + 5), avoid=result, temperature=temperature)
        added = 0
        for q in batch_qs:
            k = q.strip().lower()
            if not k or k in seen:
                continue
            seen.add(k)
            result.append(q.strip())
            added += 1
            if len(result) >= per_cat:
                break
        print(f"  {task}: round {rounds} +{added} -> {len(result)}/{per_cat}", file=sys.stderr)
        if added == 0 and rounds >= 2:  # generator is repeating; stop early
            break
    return task, result[:per_cat]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cat", type=int, default=None, help="target questions PER category (balanced)")
    ap.add_argument("--target", type=int, default=334, help="total (used only if --per-cat unset)")
    ap.add_argument("--fresh", action="store_true", help="ignore the existing bank; generate all from the model")
    ap.add_argument("--batch", type=int, default=25, help="questions requested per API call")
    ap.add_argument("--max-rounds", type=int, default=8, help="max generator calls per category")
    ap.add_argument("--out", type=Path, default=QFILE, help="output file (default data/questions.jsonl)")
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()

    load_env_file()
    qgen = load_registry().QUESTION_GENERATOR
    spec = spec_from_entry(qgen)
    if spec is None:
        sys.exit(f"question-generator key {qgen['api_key_env']} not set — fill .env (see .env.example).")
    temperature = qgen.get("temperature")  # Opus 4.8 rejects temperature -> None omits it
    print(f"question generator: {qgen['name']} ({spec.model})", file=sys.stderr)

    ncats = len(CATEGORIES)
    per_cat = args.per_cat or max(1, (args.target + ncats - 1) // ncats)

    seeds_by_task = {}
    if not args.fresh and QFILE.exists():
        for line in QFILE.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                seeds_by_task.setdefault(r.get("task", "general"), []).append(r["question"])

    def work(item):
        prefix, (task, desc) = item
        return prefix, build_category(spec, task, desc, per_cat, seeds_by_task.get(task, []),
                                       temperature=temperature, batch=args.batch, max_rounds=args.max_rounds)

    by_prefix = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for prefix, (task, qs) in ex.map(work, list(CATEGORIES.items())):
            by_prefix[prefix] = (task, qs)

    rows = []
    for prefix, (task, _desc) in CATEGORIES.items():
        _task, qs = by_prefix[prefix]
        for i, q in enumerate(qs, 1):
            rows.append({"id": f"{prefix}{i:03d}", "task": task, "question": q})

    if args.out.exists():  # never silently clobber an existing bank
        backup = args.out.with_suffix(args.out.suffix + ".bak")
        backup.write_text(args.out.read_text())
        print(f"backed up existing {args.out.name} -> {backup.name}", file=sys.stderr)

    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    from collections import Counter
    counts = Counter(r["task"] for r in rows)
    print(f"wrote {len(rows)} questions -> {args.out}  | by task: {dict(counts)}")
    short = {t: c for t, c in counts.items() if c < per_cat}
    if short:
        print(f"  ! under target ({per_cat}/cat) for: {short} — raise --max-rounds or --batch", file=sys.stderr)


if __name__ == "__main__":
    main()
