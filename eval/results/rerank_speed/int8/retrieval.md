# Retrieval eval (2026-11-16)

Golden file: `eval\golden_set.jsonl` · questions scored: 16 (comparison: 0) · skipped: 3 · companies: Infosys · k=10

Company filter: **extracted from the question** · RRF keyword weight: **0.5** · candidate pool: **20** · keyword OR-fallback pruning: **True**

Reranker: **BAAI/bge-reranker-base, candidates 20, max_length 512, int8 True**

## Headline: page tolerance 0 (non-comparison questions)

| mode | hit@1 | hit@5 | mrr@10 |
|---|---|---|---|
| dense | 0.250 | 0.688 | 0.404 |
| keyword | 0.062 | 0.500 | 0.253 |
| hybrid | 0.188 | 0.688 | 0.429 |
| hybrid_rerank | 0.375 | 0.688 | 0.508 |

## Secondary: page tolerance ±1

| mode | hit@1 | hit@5 | mrr@10 |
|---|---|---|---|
| dense | 0.250 | 0.688 | 0.416 |
| keyword | 0.125 | 0.562 | 0.308 |
| hybrid | 0.250 | 0.688 | 0.477 |
| hybrid_rerank | 0.375 | 0.688 | 0.514 |

## Latency per query (ms)

*Measured with no Docling job running (machine otherwise idle).*

| mode | p50 | p95 |
|---|---|---|
| dense | 63 | 76 |
| keyword | 40 | 108 |
| hybrid | 97 | 158 |
| hybrid_rerank | 6371 | 6698 |

## By question type (tolerance 0): Hit@5 / MRR@10

| type | n | dense | keyword | hybrid | hybrid_rerank |
|---|---|---|---|---|---|
| explanation | 1 | 0.00 / 0.10 | 0.00 / 0.00 | 0.00 / 0.11 | 0.00 / 0.00 |
| fact | 8 | 0.75 / 0.42 | 0.38 / 0.17 | 0.62 / 0.28 | 0.75 / 0.52 |
| table | 7 | 0.71 / 0.43 | 0.71 / 0.38 | 0.86 / 0.64 | 0.71 / 0.57 |

## 5 worst questions (hybrid_rerank, tolerance 0)

- **q004** (table) What was the total dividend per share for FY2026?  
  relevant: Infosys p.38, Infosys p.18 · top-5: TCS p.36, Wipro p.44, Tech Mahindra p.594, Tech Mahindra p.254, Tech Mahindra p.254
- **q012** (fact) How many clients contribute more than US$100 million in revenue, and how did that change from last year?  
  relevant: Infosys p.88 · top-5: Wipro p.27, Wipro p.362, Wipro p.486, Infosys p.319, HCLTech p.95
- **q013** (fact) How much did Infosys spend on CSR globally in fiscal 2026?  
  relevant: Infosys p.25, Infosys p.31 · top-5: Infosys p.67, Infosys p.105, Infosys p.68, Infosys p.16, Infosys p.10
- **q016** (explanation) What is Infosys's capital allocation policy for returning cash to shareholders?  
  relevant: Infosys p.38 · top-5: Infosys p.26, Infosys p.26, Infosys p.36, Infosys p.26, Infosys p.323
- **q014** (table) Under the Companies Act CSR disclosure, what total amount did Infosys spend for the financial year?  
  relevant: Infosys p.65 · top-5: Infosys p.141, Infosys p.45, Infosys p.43, Infosys p.45, Infosys p.63
