# Answer-eval error analysis

This covers the full 67-row answer eval at commit `d9fdb2c` (gpt-oss-120b answers, gpt-oss-20b
judge), before the checker and oracle-company fixes. 21 rows failed: 19 scored 0 and 2
comparisons scored 0.5 (q066, q067). Each row is assigned one cause, based on its retrieved pages,
citations and answer.

## Causes

| Cause | Count | Rows | Example |
|---|---|---|---|
| (a) Retrieval missed the page | 14 | refused: q034, q045, q051, q053, q062–q065; wrong figure from another page: q013, q030, q047, q056; question names no company, so other companies were searched: q004, q012 | q051 (Tech Mahindra net profit): the top 5 were pp.476–656, the golden pages are 19 and 22, so it refused. |
| (b) Page retrieved but refused | 1 | q035 | Wipro p.17 was retrieved at rank 2, yet the answer was a refusal. |
| (c) Wrong figure, right page available | 4 | q015, q025, q066, q067 | q066 gave Infosys's dividend as ₹71.58, which is the EPS from p.26 (expected ₹48). q025 gave TCS's statutory CSR (₹1,017 crore) instead of the global ₹1,153 crore. q067 gave Tech Mahindra's ₹15 interim dividend, not the ₹51 total. |
| (d) Checker problem | 1 | q011 | "1,965 active clients" is correct but scored 0: the checker treated "1,965" as the year 1965. |
| (e) Golden set incomplete | 0 in correctness | — | Shows up in the citation metric instead (below). |
| (f) Other | 1 | q007 | Gave "10 crore shares at ₹1,800" but not the ₹18,000 crore size: a partial answer, scored strictly. |

## Citation-page metric

28 citations are not on a golden page, and 14 of them contain an expected figure (e.g. Infosys
p.288, p.322, p.361; HCLTech p.217). The exact-page rate (0.517 at the time) therefore understates
citation accuracy: the golden page lists are incomplete. For q060, the cited pages (TCS p.58 and
HCLTech p.83) are correct but are not golden pages.

## LLM judge

The judge was fair on answers but too strict on refusals.

| Row | Faith. | Corr. | Judge reason (short) | Verdict |
|---|---|---|---|---|
| q066 | 0 | 0.5 | Infosys dividend given as ₹71.58, expected ₹48 | fair |
| q047 | 0 | 0 | lacks the key details and numbers | fair |
| q060 | 1 | 1 | both figures match and are supported | fair |
| q016 | 0 | 1 | "progressive dividend increase" not in the cited p.36 (it is on p.26 and p.38) | borderline, defensible |
| q065 | 0 | 0 | "no information" is not supported by the cited passages | too strict |

The judge gave faithfulness 0 to four refusals with no citations (q062–q065), although a refusal
makes no claims. Those zeros pulled average faithfulness down to 0.385.

## What changed after this analysis

- **Checker:** a number with a thousands separator is no longer read as a year, so q011 now
  passes.
- **Faithfulness:** refusals are left out of the average, which is now 0.556.
- **`--oracle-company`:** rows whose question names no company (q004, q008, q012) run with the
  golden company as the filter. q004 now passes; q012 now refuses.
- **Overall correctness:** 0.643 → 0.661 (checker fix) → 0.679 (oracle company). See
  [`eval/results/answers.md`](../eval/results/answers.md).
- **Prompt rules for the (c) cases** (dividend vs EPS, total vs interim, global vs statutory,
  buyback size): tried on 6 rows, they fixed none, so they were reverted. Rerank pools of 30 and 50
  scored lower than 20 and were not adopted.
