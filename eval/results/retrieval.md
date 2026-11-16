# Retrieval eval (2026-11-16)

Golden file: `eval\golden_set.jsonl` · questions scored: 16 (comparison: 0) · skipped: 3 · companies: Infosys · k=10

Company filter: **extracted from the question** · RRF keyword weight: **1.0**

## Headline: page tolerance 0 (non-comparison questions)

| mode | hit@1 | hit@5 | mrr@10 |
|---|---|---|---|
| dense | 0.250 | 0.625 | 0.389 |
| keyword | 0.062 | 0.250 | 0.160 |
| hybrid | 0.125 | 0.500 | 0.266 |
| hybrid_rerank | 0.312 | 0.562 | 0.458 |

## Secondary: page tolerance ±1

| mode | hit@1 | hit@5 | mrr@10 |
|---|---|---|---|
| dense | 0.250 | 0.625 | 0.400 |
| keyword | 0.062 | 0.250 | 0.160 |
| hybrid | 0.125 | 0.562 | 0.286 |
| hybrid_rerank | 0.312 | 0.625 | 0.471 |

## Latency per query (ms)

*Measured under load: a Docling parse (Tech Mahindra) was using the CPU during this run.*

| mode | p50 | p95 |
|---|---|---|
| dense | 99 | 216 |
| keyword | 72 | 155 |
| hybrid | 152 | 251 |
| hybrid_rerank | 10861 | 12874 |

## By question type (tolerance 0): Hit@5 / MRR@10

| type | n | dense | keyword | hybrid | hybrid_rerank |
|---|---|---|---|---|---|
| explanation | 1 | 0.00 / 0.10 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.17 |
| fact | 8 | 0.62 / 0.39 | 0.12 / 0.06 | 0.38 / 0.23 | 0.62 / 0.50 |
| table | 7 | 0.71 / 0.43 | 0.43 / 0.29 | 0.71 / 0.35 | 0.57 / 0.45 |

## 5 worst questions (hybrid_rerank, tolerance 0)

- **q004** (table) What was the total dividend per share for FY2026?  
  relevant: Infosys p.38, Infosys p.18 · top-5: Wipro p.154, TCS p.36, Infosys p.243, Wipro p.44, Infosys p.26
- **q007** (fact) What buyback did Infosys complete, in size and price per share?  
  relevant: Infosys p.38, Infosys p.16 · top-5: Infosys p.26, Infosys p.227, Infosys p.61, Infosys p.226, Infosys p.118
- **q012** (fact) How many clients contribute more than US$100 million in revenue, and how did that change from last year?  
  relevant: Infosys p.88 · top-5: Wipro p.27, Wipro p.362, Wipro p.25, Wipro p.486, Wipro p.236
- **q013** (fact) How much did Infosys spend on CSR globally in fiscal 2026?  
  relevant: Infosys p.25, Infosys p.31 · top-5: Infosys p.68, Infosys p.67, Infosys p.105, Infosys p.16, Infosys p.26
- **q005** (table) What interim dividend per share did Infosys declare for FY2026?  
  relevant: Infosys p.38 · top-5: Infosys p.36, Infosys p.323, Infosys p.26, Infosys p.119, Infosys p.243
