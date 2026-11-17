# Retrieval eval (2026-11-17)

Golden file: `eval\golden_set.jsonl` · questions scored: 56 (comparison: 8) · skipped: 11 · companies: HCLTech, Infosys, TCS, Tech Mahindra, Wipro · k=10

Company filter: **extracted from the question** · RRF keyword weight: **0.5** · candidate pool: **20** · keyword OR-fallback pruning: **True**

Reranker: **cross-encoder/ms-marco-MiniLM-L-6-v2, candidates 20, max_length 512, int8 False**

## Headline: page tolerance 0 (non-comparison questions)

| mode | hit@1 | hit@5 | mrr@10 |
|---|---|---|---|
| dense | 0.250 | 0.646 | 0.399 |
| keyword | 0.146 | 0.375 | 0.267 |
| hybrid | 0.354 | 0.688 | 0.494 |
| hybrid_rerank | 0.375 | 0.750 | 0.514 |

## Secondary: page tolerance ±1

| mode | hit@1 | hit@5 | mrr@10 |
|---|---|---|---|
| dense | 0.271 | 0.688 | 0.435 |
| keyword | 0.167 | 0.438 | 0.306 |
| hybrid | 0.396 | 0.708 | 0.539 |
| hybrid_rerank | 0.375 | 0.750 | 0.518 |

## Comparison questions (tolerance 0, one search per company, interleaved)

| mode | hit@1 | hit@5 | mrr@10 | all_companies@10 |
|---|---|---|---|---|
| dense | 0.375 | 0.500 | 0.435 | 0.250 |
| keyword | 0.000 | 0.125 | 0.093 | 0.250 |
| hybrid | 0.125 | 0.500 | 0.233 | 0.375 |
| hybrid_rerank | 0.375 | 0.500 | 0.400 | 0.250 |

## Latency per query (ms)

*Measured with no Docling job running.*

| mode | p50 | p95 |
|---|---|---|
| dense | 63 | 114 |
| keyword | 49 | 131 |
| hybrid | 90 | 203 |
| hybrid_rerank | 1249 | 2710 |

## By question type (tolerance 0): Hit@5 / MRR@10

| type | n | dense | keyword | hybrid | hybrid_rerank |
|---|---|---|---|---|---|
| comparison | 8 | 0.50 / 0.43 | 0.12 / 0.09 | 0.50 / 0.23 | 0.50 / 0.40 |
| explanation | 5 | 0.80 / 0.51 | 0.40 / 0.45 | 0.80 / 0.56 | 0.60 / 0.53 |
| fact | 26 | 0.65 / 0.39 | 0.35 / 0.24 | 0.65 / 0.46 | 0.77 / 0.51 |
| table | 17 | 0.59 / 0.38 | 0.41 / 0.26 | 0.71 / 0.53 | 0.76 / 0.52 |

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
