# Answer eval (commit d9fdb2c68134dc939d50e78ba0d23cacc3794ae8)

correct = code check (numbers / phrases), or the LLM judge's correctness for explanation and comparison rows; refusal_acc_unanswerable = share of unanswerable rows refused.

## Overall

| group | n | correct | false_refusals | refusal_acc_unanswerable | citation_retrieved | citation_golden_exact | citation_golden_pm1 | faithfulness |
|---|---|---|---|---|---|---|---|---|
| all | 67 | 0.679 | 10 | 1.0 | 1.0 | 0.608 | 0.627 | 0.556 |

## By company

| group | n | correct | false_refusals | refusal_acc_unanswerable | citation_retrieved | citation_golden_exact | citation_golden_pm1 | faithfulness |
|---|---|---|---|---|---|---|---|---|
| HCLTech | 10 | 0.75 | 1 | 1.0 | 1.0 | 0.857 | 0.857 | 0 |
| Infosys | 19 | 0.75 | 1 | 1.0 | 1.0 | 0.533 | 0.533 | 0 |
| TCS | 10 | 0.875 | 0 | 1.0 | 1.0 | 0.75 | 0.75 | 1 |
| Tech Mahindra | 10 | 0.625 | 2 | 1.0 | 1.0 | 0.429 | 0.429 | 1 |
| Wipro | 10 | 0.625 | 2 | 1.0 | 1.0 | 0.833 | 0.833 | 1 |
| comparison | 8 | 0.375 | 4 | — | 1.0 | 0.375 | 0.5 | 0.5 |

## By question type

| group | n | correct | false_refusals | refusal_acc_unanswerable | citation_retrieved | citation_golden_exact | citation_golden_pm1 | faithfulness |
|---|---|---|---|---|---|---|---|---|
| comparison | 8 | 0.375 | 4 | — | 1.0 | 0.375 | 0.5 | 0.5 |
| explanation | 5 | 0.8 | 0 | — | 1.0 | 0.5 | 0.5 | 0.6 |
| fact | 26 | 0.615 | 5 | — | 1.0 | 0.762 | 0.762 | — |
| table | 17 | 0.882 | 1 | — | 1.0 | 0.562 | 0.562 | — |
| unanswerable | 11 | — | 0 | 1.0 | — | — | — | — |

Tokens: {'openai/gpt-oss-20b': 29570, 'openai/gpt-oss-120b': 144384} · per question 2596 · latency p50/p95 53644/59641 ms (includes waits on the Groq rate limit)

## Failed rows

- **q007** (fact) What buyback did Infosys complete, in size and price per share? — expected figure not found
- **q012** (fact) How many clients contribute more than US$100 million in revenue, and how did that change from last year? — refused
- **q013** (fact) How much did Infosys spend on CSR globally in fiscal 2026? — expected figure not found
- **q015** (fact) How much has Infosys returned to shareholders for fiscal 2026? — expected figure not found
- **q025** (fact) How much did TCS spend on CSR globally in FY2026? — expected figure not found
- **q030** (table) What was Wipro's consolidated revenue from operations in FY2026, in Indian rupees million? — expected figure not found
- **q034** (table) What was Wipro's voluntary attrition (excluding DOP) in FY26? — refused
- **q035** (fact) What percentage of Wipro's employees were women in FY2026 (highlights)? — refused
- **q045** (fact) What share of HCLTech's workforce were women in FY2026 (highlights)? — refused
- **q047** (explanation) Why did HCLTech's consolidated net profit ratio fall in FY26? — Answer lacks the key details and numbers from the expected answer.
- **q051** (fact) What was Tech Mahindra's net profit for FY2026, in rupees crore? — refused
- **q053** (fact) What was Tech Mahindra's global headcount as on March 31, 2026? — refused
- **q056** (fact) How much did Tech Mahindra spend on CSR in financial year 2025-26? — expected figure not found
- **q062** (comparison) Compare the year-end employee numbers of HCLTech and Tech Mahindra for FY2026. — Answer does not provide the requested employee numbers.
- **q063** (comparison) Compare the headcount of TCS and Infosys at the end of FY2026. — Answer does not provide the required numbers.
- **q064** (comparison) Compare attrition at Wipro and HCLTech in FY2026. — Answer does not provide the required figures
- **q065** (comparison) Compare the IT attrition of TCS and Tech Mahindra in FY2026. — The answer states there is no information, which is not supported by the cited passages and does not match the expected data.
- **q066** (comparison) Compare the total dividend per share of TCS and Infosys for FY2026. — The answer incorrectly states Infosys dividend as ₹71.58, whereas the expected answer is ₹48 per share.
- **q067** (comparison) Compare the total dividend per share of HCLTech and Tech Mahindra for FY2026. — The answer does not provide the correct total dividend per share for Tech Mahindra, contradicting the expected answer.
