# Judge Trustworthiness Report

**Judge model:** `gpt-5.6-luna`  |  **Bootstrap draws:** 1000  |  **Pairs:** 1500

Auditing the LLM-as-judge with paired synthetic controls — the
*"audit the auditor"* method, ported from fairness audits to LLM evaluation.

## Validation record

| # | Metric | Value (95% CI) | Reads as |
|---|--------|----------------|----------|
| 1 | Negative control — spurious decisive rate | 0.408 [0.371, 0.450] | judge invents a winner on equivalent pairs this often (lower = better) |
| 2 | Negative control — content-side skew | 0.490 [0.433, 0.554] | P(picks ans1 \| decisive); 0.5 = no systematic side preference |
| 3 | Positive #1 — first-position rate | 0.588 [0.552, 0.622] | 0.5 = no primacy bias; >0.5 = favors the first-shown answer |
| 4 | Positive #1 — order-flip rate | 0.203 [0.181, 0.223] | verdict changes under a pure order swap this often |
| 5 | Positive #2 — prefers-longer rate | 0.547 [0.503, 0.588] | 0.5 = no length bias; >0.5 = favors the longer answer on content-equal pairs |
| 6 | Discrimination (sanity) | 0.961 [0.946, 0.975] | picks the strong answer on strong-vs-weak pairs (should be high) |
| 7 | BH-FDR significant biases | 6 of 15 tests | tasks/dimensions flagged after multiplicity correction |

![negative control](figures/negative_control.png)
![position bias](figures/position_bias.png)
![verbosity bias](figures/verbosity_bias.png)

## FDR table (Benjamini–Hochberg, two-sided binomial vs the null)

| label                          |   k |   n |   rate |   p_null |   p_raw |   q_bh | sig_fdr   |
|:-------------------------------|----:|----:|-------:|---------:|--------:|-------:|:----------|
| neg::advice::side_skew         |  73 | 152 |  0.480 |    0.500 |   0.685 |  0.836 | False     |
| neg::coding::side_skew         |  37 |  59 |  0.627 |    0.500 |   0.067 |  0.145 | False     |
| neg::knowledge::side_skew      |  64 | 129 |  0.496 |    0.500 |   1.000 |  1.000 | False     |
| neg::reasoning::side_skew      |   4 |  15 |  0.267 |    0.500 |   0.118 |  0.222 | False     |
| neg::writing::side_skew        |  22 |  53 |  0.415 |    0.500 |   0.272 |  0.430 | False     |
| pos::advice::first_position    |  95 | 152 |  0.625 |    0.500 |   0.003 |  0.006 | True      |
| pos::coding::first_position    |  33 |  59 |  0.559 |    0.500 |   0.435 |  0.593 | False     |
| pos::knowledge::first_position |  67 | 129 |  0.519 |    0.500 |   0.725 |  0.836 | False     |
| pos::reasoning::first_position |   7 |  15 |  0.467 |    0.500 |   1.000 |  1.000 | False     |
| pos::writing::first_position   |  38 |  53 |  0.717 |    0.500 |   0.002 |  0.006 | True      |
| len::advice::picks_longer      | 134 | 200 |  0.670 |    0.500 |   0.000 |  0.000 | True      |
| len::coding::picks_longer      | 103 | 151 |  0.682 |    0.500 |   0.000 |  0.000 | True      |
| len::knowledge::picks_longer   | 107 | 198 |  0.540 |    0.500 |   0.286 |  0.430 | False     |
| len::reasoning::picks_longer   |  40 |  51 |  0.784 |    0.500 |   0.000 |  0.000 | True      |
| len::writing::picks_longer     |  42 | 179 |  0.235 |    0.500 |   0.000 |  0.000 | True      |

## How to read this

- **Negative control (1–2)** = the paper's `Y_clean`: on pairs with no true quality
  difference, a calibrated judge should mostly tie with no systematic side preference.
  A high decisive rate or a side-skew CI excluding 0.5 means the judge *manufactures*
  preferences.
- **Positive controls (3–5)** inject *known* biases — presentation order and answer
  length. An unbiased judge is invariant to both: first-position rate ≈ 0.5, low flip
  rate, prefers-longer rate ≈ 0.5. A CI that excludes 0.5 is the audit *recovering a
  known bias*, exactly as `Y_inject` recovers a planted effect. The two axes are
  orthogonal (each pair is shown in both orders).
- **Discrimination (6)** guards against a degenerate "always tie" judge: it must still
  pick the better answer when one genuinely is better.
- **FDR (7)** controls false discoveries across the many per-task tests.

The verdict is a *distribution* (every line carries a bootstrap CI), not a single token.
