# R6 latency: before vs after

| Metric | Before (Milestone 2) | After, same questions | After, all (60-question set) |
|---|---:|---:|---:|
| Runs | 51 | 51 | 150 |
| Questions | 17 | 17 | 50 |
| p50, all runs (s) | 0.9 | 6.4 | 7.8 |
| p95, all runs (s) | 35.7 | 16.7 | 24.8 |
| p50, answered (s) | 12.0 | 11.5 | 12.2 |
| p95, answered (s) | 39.1 | 32.1 | 27.6 |
| Runs over 15 s | 6 | 5 | 30 |
| Completion tokens / run | 117.7 | 143.3 | 172.3 |

Target: p50 latency on answered questions < 15 s -> **met**

## Time and tokens per agent step (after, mean per run)

| Step | Mean time (s) | Share of total | LLM calls | Prompt tokens | Completion tokens |
|---|---:|---:|---:|---:|---:|
| schema_retriever | 0.08 | 1% | 0.00 | 0 | 0 |
| sql_generator | 2.86 | 33% | 1.33 | 432 | 57 |
| safety_verifier | 0.00 | 0% | 0.00 | 0 | 0 |
| syntax_verifier | 0.00 | 0% | 0.00 | 0 | 0 |
| semantic_verifier | 2.50 | 28% | 0.64 | 229 | 51 |
| optimizer | 0.68 | 8% | 0.07 | 32 | 15 |
| executor | 0.00 | 0% | 0.00 | 0 | 0 |
| result_verifier | 1.10 | 12% | 0.62 | 181 | 22 |
| response_generator | 1.58 | 18% | 0.61 | 344 | 28 |
| repair | 0.00 | 0% | 0.00 | 0 | 0 |
| schema_retry | 0.00 | 0% | 0.00 | 0 | 0 |

Milestone 2 traces logged only end-to-end latency, so 'before' has no per-step split.
