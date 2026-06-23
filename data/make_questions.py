"""Expand data/questions.jsonl to a larger, diverse bank using the generator model.

Keeps the curated seed questions, then asks the model for more per task category,
dedupes, and writes them back. Reproducible enough for an audit: questions are
generic and self-contained; the audit's validity does not depend on which exact
questions are used, only that they are diverse and answerable.

Run (needs OC_GEN_*/OC_JUDGE_*):
    python data/make_questions.py --target 334
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
from llm_client import ModelSpec, chat  # noqa: E402

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


def gen_category(spec, desc, n) -> list[str]:
    prompt = (
        f"Generate {n} diverse, self-contained {desc}. "
        "Each must be a single question or instruction answerable in a few sentences "
        "with no external context, files, or images. Keep them varied and non-redundant. "
        'Return ONLY a JSON array of strings, e.g. ["...", "..."].'
    )
    raw = chat(spec, [{"role": "user", "content": prompt}], temperature=1.0, max_tokens=4000)
    return _parse_list(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=334, help="total questions desired")
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()

    spec = ModelSpec.from_env("GEN")
    seeds = [json.loads(l) for l in QFILE.read_text().splitlines() if l.strip()]
    per_cat = max(1, (args.target + len(CATEGORIES) - 1) // len(CATEGORIES))

    def work(item):
        prefix, (task, desc) = item
        return prefix, task, gen_category(spec, desc, per_cat)

    generated = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for prefix, task, qs in ex.map(work, list(CATEGORIES.items())):
            generated[prefix] = (task, qs)
            print(f"  {task}: generated {len(qs)}", file=sys.stderr)

    seen = {q["question"].strip().lower() for q in seeds}
    rows = list(seeds)
    counters = {p: 900 for p in CATEGORIES}  # generated ids start high to avoid colliding with seeds
    for prefix, (task, qs) in generated.items():
        for q in qs:
            key = q.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            counters[prefix] += 1
            rows.append({"id": f"{prefix}{counters[prefix]}", "task": task, "question": q})

    rows = rows[: args.target]
    QFILE.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    from collections import Counter
    print(f"wrote {len(rows)} questions -> {QFILE}  | by task: {dict(Counter(r['task'] for r in rows))}")


if __name__ == "__main__":
    main()
