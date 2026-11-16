# Retrieval eval (2026-11-16)

Golden file: `eval\golden_set.jsonl` · questions scored: 16 (comparison: 0) · skipped: 3 · companies: Infosys · k=10

Company filter: **golden companies (oracle, diagnostic)** · RRF keyword weight: **1.0**

## Headline: page tolerance 0 (non-comparison questions)

| mode | hit@1 | hit@5 | mrr@10 |
|---|---|---|---|
| dense | 0.250 | 0.625 | 0.396 |
| keyword | 0.062 | 0.250 | 0.169 |
| hybrid | 0.125 | 0.500 | 0.276 |
| hybrid_rerank | 0.312 | 0.688 | 0.510 |

## Secondary: page tolerance ±1

| mode | hit@1 | hit@5 | mrr@10 |
|---|---|---|---|
| dense | 0.250 | 0.625 | 0.408 |
| keyword | 0.062 | 0.250 | 0.169 |
| hybrid | 0.125 | 0.562 | 0.305 |
| hybrid_rerank | 0.312 | 0.750 | 0.523 |

## Latency per query (ms)

*Measured under load: a Docling parse (Tech Mahindra) was using the CPU during this run.*

| mode | p50 | p95 |
|---|---|---|
| dense | 113 | 948 |
| keyword | 99 | 238 |
| hybrid | 231 | 590 |
| hybrid_rerank | 10535 | 12323 |

## By question type (tolerance 0): Hit@5 / MRR@10

| type | n | dense | keyword | hybrid | hybrid_rerank |
|---|---|---|---|---|---|
| explanation | 1 | 0.00 / 0.10 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.17 |
| fact | 8 | 0.62 / 0.39 | 0.12 / 0.08 | 0.38 / 0.23 | 0.75 / 0.54 |
| table | 7 | 0.71 / 0.45 | 0.43 / 0.29 | 0.71 / 0.37 | 0.71 / 0.52 |

## 5 worst questions (hybrid_rerank, tolerance 0)

- **q007** (fact) What buyback did Infosys complete, in size and price per share?  
  relevant: Infosys p.38, Infosys p.16 · top-5: Infosys p.26, Infosys p.227, Infosys p.61, Infosys p.226, Infosys p.118
- **q013** (fact) How much did Infosys spend on CSR globally in fiscal 2026?  
  relevant: Infosys p.25, Infosys p.31 · top-5: Infosys p.68, Infosys p.67, Infosys p.105, Infosys p.16, Infosys p.26
- **q005** (table) What interim dividend per share did Infosys declare for FY2026?  
  relevant: Infosys p.38 · top-5: Infosys p.36, Infosys p.323, Infosys p.26, Infosys p.119, Infosys p.243
- **q006** (table) What final dividend per share did Infosys recommend for FY2026?  
  relevant: Infosys p.38 · top-5: Infosys p.323, Infosys p.36, Infosys p.361, Infosys p.243, Infosys p.26
- **q016** (explanation) What is Infosys's capital allocation policy for returning cash to shareholders?  
  relevant: Infosys p.38 · top-5: Infosys p.26, Infosys p.26, Infosys p.26, Infosys p.36, Infosys p.36
