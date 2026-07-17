<h1 align="center">Auditing the LLM-as-Judge</h1>
<p align="center"><em>Paired synthetic controls that calibrate the judge before you trust its verdicts.</em></p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10-blue.svg" alt="python 3.10">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT">
  <img src="https://img.shields.io/badge/harness-OpenCompass-orange.svg" alt="OpenCompass">
  <img src="https://img.shields.io/badge/stats-bootstrap%20%2B%20BH--FDR-purple.svg" alt="bootstrap + FDR">
</p>

---

Modern benchmarks increasingly are an LLM judge. We trust that judge to rank
answers — but who calibrates the judge? A judge that silently invents preferences where
none exist, or quietly prefers whichever answer is shown first (or simply the longer
one), corrupts every leaderboard built on top of it.

The fix isn't another accuracy score for the judge. It's a **calibration record on the
very data it judges**: evidence that the judge does *not* manufacture a winner under a
known null, and *does* reveal a known bias when one is injected. That is exactly the
structure of **paired synthetic controls** — negative-outcome controls + simulation-based
calibration — here pointed at a judge instead of a hiring audit.

> **TL;DR** — Build pairs where the truth is known, run them through the judge in both
> orders and at two lengths, and report a one-page **Judge Trustworthiness Report** with
> bootstrap CIs and FDR correction. A judge "passes" only if it stays calibrated on the
> nulls *and* surfaces the planted biases.

## Results — five LLM judges, head-to-head

The headline result: **GPT-5.6 Luna, Claude Sonnet 5, Gemini 3.5 Flash, Kimi K2.6, and
DeepSeek V4** audited as pairwise judges over the *same* comparison set, with each one's
calibration record stacked side by side — negative control (does it invent preferences?),
position + length bias (does it recover known biases?), quality discrimination, and
BH-FDR significance. Because every judge scores identical pairs, each difference is the
judge's, not the data's.

All five judges scored the **same 500-question comparison set** — 500 × 3 pair types × 2
orders = **3,000 judge calls each**, 15,000 total. Questions were written by a neutral
third party (Claude Opus 4.8); answer pairs by a fixed generator (DeepSeek V4). Full record
+ per-task tables: [`docs/judge_comparison.md`](docs/judge_comparison.md); each judge's own
single-judge report (all seven metrics + figures) is under [`docs/reports/`](docs/reports/).

<p align="center"><img src="docs/figures_compare/comparison.png" width="100%"></p>

| Judge | Neg: spurious-decisive ↓ | Pos: first-position | Pos: prefers-longer | Discrimination ↑ | FDR-sig |
|---|---|---|---|---|---|
| `gpt-5.6-luna` | 0.41 | 0.59 ⚠️ primacy | **0.55** — least length bias | 0.96 | 6/15 |
| `claude-sonnet-5` | 0.50 | 0.39 ⚠️ recency (strongest) | 0.78 ⚠️ | 0.98 | 8/15 |
| `gemini-3.5-flash` | 0.46 | 0.45 ⚠️ recency | 0.88 ⚠️ | 0.99 | 5/15 |
| `kimi-k2.6` | 0.25 ✅ | 0.64 ⚠️ primacy | 0.88 ⚠️ | 0.99 | 5/15 |
| `deepseek-v4` | **0.13** ✅ ties most | 0.58 ⚠️ primacy | 0.96 ⚠️ most length bias | **1.00** | 5/15 |

**Read it — three findings:**

1. **Length bias is universal but stratified.** Every judge prefers the longer of two
   content-equivalent answers, but the magnitude ranges from mild (**Luna 0.55**) to near-
   absolute (**DeepSeek 0.96**). This is exactly the bias a leaderboard built on the wrong
   judge would silently inherit.
2. **Position bias splits the field into two camps.** Luna, Kimi and DeepSeek favor the
   **first**-shown answer (primacy); Sonnet 5 and Gemini favor the **second** (recency),
   with Sonnet the most order-sensitive.
3. **No judge is clean, and the strengths trade off.** The best negative-control performer
   (DeepSeek — ties genuinely-equivalent pairs 87% of the time) is also the most length-
   biased; the least length-biased (Luna) over-decides on equivalent pairs. All five
   discriminate quality reliably (≥0.96), so the failures are *calibration*, not competence.

Reproduce the table + figure from committed verdicts (no API key needed):
`python src/compare_report.py docs/verdicts/verdicts_*.jsonl` — or run the whole pipeline
end to end with `bash scripts/run_compare.sh`.

> *No-API-key demo?* A synthetic judge with planted biases lives under
> [`docs/sample/`](docs/sample/) — regenerate with `python scripts/make_sample.py`.

## The idea in one table

| Fairness audit (the source method) | This project (LLM-judge audit) |
|---|---|
| Negative control `Y_clean` — strip the real effect | **Equivalent answer pairs** — two samples of the *same* model on the same question (no true quality gap) |
| *"the audit must not invent disparities"* | the judge must not invent a preference → **spurious-decisive rate** + **content-side skew** |
| Positive control `Y_inject` — plant a known effect θ | **Inject known biases** — show every pair in both orders, and at two lengths |
| *"the audit must recover θ at advertised coverage"* | **first-position rate** (primacy) and **prefers-longer rate** (length); 0.5 = unbiased |
| Verdict is a Monte-Carlo *distribution*, not a token | **Bootstrap 95% CIs** on every rate (cluster-bootstrap over pairs) |
| BH-FDR across many groups | **BH-FDR** across many tasks × bias dimensions |
| Six-line validation record | one-page **`judge_trust_report.md`** |

Two injected-bias axes ship today — **position** (order swap) and **verbosity** (concise
vs. a separately generated detailed answer) — and they're orthogonal because every pair
is shown in both orders. The same machinery extends to self-preference or formatting bias
by swapping the perturbation.

## What's here

```
audit-the-judge/
  configs/    eval_judge_min.py        # learn the OpenCompass judge data-flow (smoke)
              eval_pairwise_audit.py   # run our pairs through the judge inside OpenCompass
              models.py                # judge registry for the multi-judge comparison
  data/       questions.jsonl          # seed questions across 5 task types
              make_questions.py        # (re)build the bank with the QUESTION_GENERATOR
              build_pairs.py           # -> pairs.jsonl  (null + strong/weak + verbose, both orders)
  src/        run_judge.py             # OpenAI-compatible pairwise judge (resumable)
              run_compare.py           # build once -> judge with every model -> compare
              registry.py              # load configs/models.py + .env (shared)
              parse_outputs.py         # OC results OR judge dump -> one tidy verdict table
              negative_control.py      # spurious-preference rate on equivalent pairs
              position_bias.py         # first-position + flip rate (primacy axis)
              verbosity_bias.py        # prefers-longer rate (length axis)
              stats.py                 # bootstrap CIs + BH-FDR
              report.py                # figures + the one-page report (single judge)
              compare_report.py        # stack N judges into one comparison + figure
  tests/      test_audit.py            # plants known biases, asserts the audit recovers them
  scripts/    setup_env.sh  run_smoke.sh  run_audit.sh  run_compare.sh  make_sample.py
  docs/sample/                         # committed synthetic example output
```

**Decoupled from OpenCompass internals.** `parse_outputs.py` normalizes either an
OpenCompass results dir *or* the `run_judge.py` dump into a single schema
`(pair_id, task, pair_type, true_label, order, verdict_slot, winner)`. Every statistic
reads that schema, so the analysis is stable as OpenCompass's output format changes
across versions. `run_judge.py` is the tested path for the statistics; OpenCompass is
used to learn the harness and cross-check the judge.

## Quickstart

Any OpenAI-compatible endpoint works as the judge (DeepSeek, OpenAI, a local vLLM
server, …); DeepSeek is the cheap default.

```bash
# 0. environment  (installs Miniconda if absent, clones OpenCompass, installs everything)
bash scripts/setup_env.sh && conda activate oc
cp .env.example .env        # fill in OC_JUDGE_MODEL / OC_JUDGE_API_KEY / OC_JUDGE_API_BASE
source .env

# 1-2. learn the OpenCompass LLM-judge data flow (one tiny eval)
bash scripts/run_smoke.sh   # -> outputs/judge_min/<ts>/{summary/*.csv, results/**/*.json}

# 3-7. the audit: build pairs -> judge -> controls + bootstrap + FDR -> report
bash scripts/run_audit.sh                 # ~40 questions
#   N=20 bash scripts/run_audit.sh        # quick
#   OFFLINE=1 bash scripts/run_audit.sh   # no API key: fabricated answers (plumbing test)
```

Outputs land in `outputs/judge_trust_report.md` and `outputs/figures/`.

### Verify the tooling without an API key

```bash
python tests/test_audit.py
```

Plants a 70% primacy bias and a 75% length bias into synthetic verdict streams and
asserts the audit flags each (CI excludes 0.5, BH-FDR significant), then plants a
calibrated judge and asserts it passes cleanly — the positive-control sanity check
applied to the tooling itself.

## Comparing multiple judges

To audit several judges side by side — e.g. **GPT-5.6 Luna, Claude Sonnet 5, Gemini 3.5
Flash, Kimi K2.6, DeepSeek V4** — each is scored on the **same** pairs so any difference is
the judge's, not the data's.
Every provider exposes an OpenAI-compatible endpoint, so the one `llm_client` drives all
of them; only `(model, api_base, api_key)` change.

Three roles are kept **separate** so nothing under audit authors its own test
(`configs/models.py`):

| role | what it does | default |
|---|---|---|
| `QUESTION_GENERATOR` | writes the seed question bank | Claude Opus 4.8 (neutral third party) |
| `GENERATOR` | writes the A/B answer pairs (same for every judge) | DeepSeek V4 (`deepseek-chat`) |
| `JUDGES` | the models being audited + compared | GPT-5.6 Luna, Claude Sonnet 5, Gemini 3.5 Flash, Kimi K2.6, DeepSeek V4 |

```bash
# 1. register models + edit IDs to what you can call (keys stay in .env)
#    configs/models.py
# 2. put one key per provider in .env (see .env.example), then source it
cp .env.example .env && $EDITOR .env && source .env

# 3. (optional) regenerate a balanced question bank with the neutral QUESTION_GENERATOR
python data/make_questions.py --per-cat 100 --fresh   # -> 100 x 5 = 500 questions, all Opus

# 4. build pairs once with the generator, judge them with every model, compare
bash scripts/run_compare.sh                       # all judges that have a key set
N=40 bash scripts/run_compare.sh                  # 40 questions (cheaper first pass)
ONLY="gpt-5.6-luna kimi-k2.6" bash scripts/run_compare.sh   # a subset (names from configs/models.py)
```

| provider | `api_base` (in `configs/models.py`) | key env var |
|---|---|---|
| OpenAI (ChatGPT) | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| Anthropic (Claude) | `https://api.anthropic.com/v1/` | `ANTHROPIC_API_KEY` |
| Google (Gemini) | `https://generativelanguage.googleapis.com/v1beta/openai/` | `GEMINI_API_KEY` |
| Moonshot (Kimi) | `https://api.moonshot.ai/v1` | `MOONSHOT_API_KEY` |
| DeepSeek | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |

Outputs:
- `outputs/judge_comparison.md` — one validation-record row per judge + a grouped-bar
  figure (`outputs/figures_compare/comparison.png`).
- `outputs/reports/<judge>/judge_trust_report.md` — the full single-judge report for each.

Runs are **resumable** and **fair by construction**: pairs are generated once by the
fixed `GENERATOR` (so no judge is scoring different content), each judge's verdicts are
cached per `(pair_id, order)`, and a judge whose key is missing is skipped rather than
aborting the run. Re-run to add a judge or retry failed calls. Full-set cost per judge is
~`3 × 2 × N` judge calls (`N` = questions; the shipped bank has 500).

## The validation record

`run_audit.sh` produces a seven-line record (the LLM-judge analogue of the paper's record):

| # | Metric | Reads as |
|---|---|---|
| 1 | Negative — spurious decisive rate | how often the judge picks a winner on equivalent pairs (lower = better) |
| 2 | Negative — content-side skew | P(picks answer-1 \| decisive); 0.5 = no systematic side preference |
| 3 | Positive #1 — first-position rate | 0.5 = no primacy bias; >0.5 = favors the first-shown answer |
| 4 | Positive #1 — order-flip rate | how often the verdict flips under a pure order swap |
| 5 | Positive #2 — prefers-longer rate | 0.5 = no length bias; >0.5 = favors the longer of two content-equal answers |
| 6 | Discrimination (sanity) | picks the strong answer on strong-vs-weak pairs (guards against an "always tie" judge) |
| 7 | BH-FDR significant biases | per-task × per-axis biases surviving multiplicity correction |

## Fix log: a bug the audit caught on itself

The length probe shipped broken the first time, and the framework's own output is what
exposed it — worth keeping as a worked example of why the controls are distributional.

- **The bug.** The "long" answer was built as `concise_answer + boilerplate filler`.
  That isn't a content-equivalent length contrast; it's a literal superset with obvious
  padding. A competent judge (further told to *ignore length*) correctly preferred the
  un-padded answer **every single time**.
- **The false finding it produced.** `prefers-longer` came out **exactly 0.000 on all
  five tasks (0/27, 0/35, 0/64, …)** with a **zero-width CI**, and BH-FDR then stamped it
  "significant" — because 0 is far from 0.5, the binomial p-value is tiny. Read naively,
  the report "significantly" announced a length bias that was 100% a pipeline artifact.
- **How the audit flagged its own bug.** A real behavioral rate is never *exactly* 0 on
  every task with no spread — you'd see 0.3/0.4 with a CI that has width. A proportion
  pinned at a boundary with a zero-width CI *yet called significant* is the fingerprint of
  a mis-constructed metric, not a real effect. The bootstrap + FDR combination is what
  made that fingerprint visible.
- **The fix.** Generate two genuinely content-equivalent answers — a concise one and a
  detailed one (both asked to be correct and complete) — instead of `concise + filler`,
  and re-judge just the verbosity slice (~668 calls, thanks to the resumable runner). The
  honest result flipped to **0.940**: a real, well-estimated length bias. (This is the
  single-judge DeepSeek run on 334 questions in [`docs/real/`](docs/real/); the headline
  multi-judge table above reports DeepSeek at 0.96 on the newer 500-question set — the same
  bias, a different run.)
- **Caveat that remains.** "Longer" and "more thorough" are correlated, so part of the
  0.940 is a legitimate preference for detail; the probe measures *prefers-longer*, not
  *prefers-fluff*. That nuance is the kind of thing a validation record should state
  out loud rather than bury.

## Scope & honesty

- **What it checks:** calibration of the judge's *pairwise verdicts* on the realized
  comparison set — specificity (no invented preferences) and recovery of known biases.
- **What it does not check:** not a construct-validity or adversarial-robustness proof. A
  judge gamed to hide a bias on an axis we didn't probe can still pass — the controls
  raise the floor, they don't certify the ceiling (same caveat as the source method).
- **Extending the positive control:** position and verbosity ship today; the same
  both-orders machinery extends to self-preference or markdown-formatting bias.

## Credit

Method adapted from *"Auditing the Auditor: Paired Synthetic Controls for Calibrating
Fairness Audits"* (negative-outcome controls; simulation-based calibration). Harness:
[OpenCompass](https://github.com/open-compass/opencompass). Licensed MIT.
