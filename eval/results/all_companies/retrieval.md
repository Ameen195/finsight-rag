# Retrieval eval (2026-11-17)

Golden file: `eval\golden_set.jsonl` · questions scored: 32 (comparison: 0) · skipped: 7 · companies: Infosys, TCS, Wipro · k=10

Company filter: **extracted from the question** · RRF keyword weight: **0.5** · candidate pool: **20** · keyword OR-fallback pruning: **True**

Reranker: **cross-encoder/ms-marco-MiniLM-L-6-v2, candidates 20, max_length 512, int8 False**

## Headline: page tolerance 0 (non-comparison questions)

| mode | hit@1 | hit@5 | mrr@10 |
|---|---|---|---|
| dense | 0.250 | 0.688 | 0.408 |
| keyword | 0.156 | 0.469 | 0.310 |
| hybrid | 0.344 | 0.719 | 0.517 |
| hybrid_rerank | 0.438 | 0.812 | 0.584 |

## Secondary: page tolerance ±1

| mode | hit@1 | hit@5 | mrr@10 |
|---|---|---|---|
| dense | 0.250 | 0.750 | 0.437 |
| keyword | 0.188 | 0.531 | 0.344 |
| hybrid | 0.406 | 0.750 | 0.572 |
| hybrid_rerank | 0.438 | 0.812 | 0.588 |

## Latency per query (ms)

*Measured with no Docling job running.*

| mode | p50 | p95 |
|---|---|---|
| dense | 71 | 144 |
| keyword | 45 | 150 |
| hybrid | 92 | 143 |
| hybrid_rerank | 1338 | 1460 |

## By question type (tolerance 0): Hit@5 / MRR@10

| type | n | dense | keyword | hybrid | hybrid_rerank |
|---|---|---|---|---|---|
| explanation | 3 | 0.67 / 0.43 | 0.33 / 0.37 | 0.67 / 0.48 | 0.67 / 0.50 |
| fact | 16 | 0.81 / 0.48 | 0.44 / 0.29 | 0.75 / 0.52 | 0.88 / 0.63 |
| table | 13 | 0.54 / 0.31 | 0.54 / 0.32 | 0.69 / 0.52 | 0.77 / 0.55 |

## 5 worst questions (hybrid_rerank, tolerance 0)

- **q004** (table) What was the total dividend per share for FY2026?  
  relevant: Infosys p.38, Infosys p.18 · top-5: Wipro p.44, Tech Mahindra p.254, Tech Mahindra p.255, TCS p.325, TCS p.36
- **q012** (fact) How many clients contribute more than US$100 million in revenue, and how did that change from last year?  
  relevant: Infosys p.88 · top-5: HCLTech p.95, HCLTech p.95, Wipro p.27, Wipro p.362, Wipro p.486
- **q013** (fact) How much did Infosys spend on CSR globally in fiscal 2026?  
  relevant: Infosys p.25, Infosys p.31 · top-5: Infosys p.68, Infosys p.67, Infosys p.105, Infosys p.16, Infosys p.10
- **q016** (explanation) What is Infosys's capital allocation policy for returning cash to shareholders?  
  relevant: Infosys p.38 · top-5: Infosys p.36, Infosys p.26, Infosys p.36, Infosys p.321, Infosys p.242
- **q030** (table) What was Wipro's consolidated revenue from operations in FY2026, in Indian rupees million?  
  relevant: Wipro p.284 · top-5: Wipro p.96, Wipro p.387, Wipro p.28, Wipro p.45, Wipro p.403
