# Judge Comparison Report

**Judges:** 5  |  **Bootstrap draws:** 1000  |  every judge scored the **same** `data/pairs.jsonl`

Each judge is audited with the same paired synthetic controls as the single-judge report
(*"audit the auditor"*, ported to LLM-as-judge). Because the answer pairs are identical
across judges, every difference below is a property of the **judge**, not the data.

## Comparison record

| Judge | Pairs | Neg: spurious-decisive | Neg: side-skew | Pos: first-position | Pos: prefers-longer | Discrimination | FDR-sig |
|---|---|---|---|---|---|---|---|
| `gpt-5.6-luna` | 1500 | 0.408 [0.371, 0.450] ⚠️ manufactures | 0.490 [0.433, 0.554] | 0.588 [0.552, 0.622] ⚠️ favors first | 0.547 [0.503, 0.588] ⚠️ favors longer | 0.961 [0.946, 0.975] ✅ discriminates | 6/15 |
| `claude-sonnet-5` | 1492 | 0.496 [0.460, 0.534] ⚠️ manufactures | 0.485 [0.432, 0.539] | 0.387 [0.358, 0.415] ⚠️ favors first (reversed) | 0.779 [0.744, 0.811] ⚠️ favors longer | 0.981 [0.967, 0.991] ✅ discriminates | 8/15 |
| `gemini-3.5-flash` | 1500 | 0.455 [0.416, 0.493] ⚠️ manufactures | 0.524 [0.466, 0.585] | 0.447 [0.421, 0.472] ⚠️ favors first (reversed) | 0.880 [0.850, 0.905] ⚠️ favors longer | 0.986 [0.975, 0.994] ✅ discriminates | 5/15 |
| `kimi-k2.6` | 1498 | 0.246 [0.216, 0.278] ✅ mostly ties | 0.494 [0.426, 0.563] | 0.637 [0.586, 0.688] ⚠️ favors first | 0.876 [0.848, 0.901] ⚠️ favors longer | 0.986 [0.978, 0.994] ✅ discriminates | 5/15 |
| `deepseek-v4` | 1500 | 0.131 [0.107, 0.158] ✅ mostly ties | 0.534 [0.427, 0.638] | 0.580 [0.508, 0.648] ⚠️ favors first | 0.961 [0.946, 0.973] ⚠️ favors longer | 0.995 [0.988, 1.000] ✅ discriminates | 5/15 |

![judge comparison](figures_compare/comparison.png)

## How to read this

- **Neg: spurious-decisive** — on equivalent pairs (no true quality gap), how often the
  judge invents a winner. Lower is better; a calibrated judge mostly ties.
- **Neg: side-skew** — among decisive null verdicts, P(picks answer-1). 0.5 = no
  content-side preference (a CI excluding 0.5 is a systematic side bias).
- **Pos: first-position** — primacy bias. 0.5 = order-invariant; >0.5 favors whichever
  answer is shown first. A CI excluding 0.5 is the control *recovering* a real bias.
- **Pos: prefers-longer** — length bias on concise-vs-detailed content-equal pairs.
  0.5 = no length preference; >0.5 favors the longer answer.
- **Discrimination** — sanity check: picks the strong answer on strong-vs-weak pairs.
  Should be high; guards against a degenerate "always tie" judge.
- **FDR-sig** — per-task × per-axis biases surviving Benjamini–Hochberg correction.

Each cell carries a bootstrap 95% CI (cluster-bootstrap over pairs): the verdict is a
*distribution*, not a single token. A judge to trust as a leaderboard backbone ties the
nulls, sits near 0.5 on both positive axes, and discriminates quality reliably.
