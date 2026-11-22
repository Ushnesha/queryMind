# R6 latency: before vs after

| Metric | Before (Milestone 2) | After, same questions | After, all (60-question set) |
|---|---:|---:|---:|
| Runs | 51 | 51 | 180 |
| Questions | 17 | 17 | 60 |
| p50, all runs (s) | 0.9 | 6.4 | 8.2 |
| p95, all runs (s) | 35.7 | 16.7 | 24.8 |
| p50, answered (s) | 12.0 | 11.5 | 11.5 |
| p95, answered (s) | 39.1 | 32.1 | 26.6 |
| Runs over 15 s | 6 | 5 | 32 |
| Completion tokens / run | 117.7 | 143.3 | 175.4 |

Target: p50 latency on answered questions < 15 s -> **met**

## Time and tokens per agent step (after, mean per run)

| Step | Mean time (s) | Share of total | LLM calls | Prompt tokens | Completion tokens |
|---|---:|---:|---:|---:|---:|
| schema_retriever | 0.11 | 1% | 0.00 | 0 | 0 |
| sql_generator | 2.96 | 33% | 1.38 | 451 | 59 |
| safety_verifier | 0.00 | 0% | 0.00 | 0 | 0 |
| syntax_verifier | 0.00 | 0% | 0.00 | 0 | 0 |
| semantic_verifier | 2.65 | 30% | 0.67 | 239 | 54 |
| optimizer | 0.56 | 6% | 0.06 | 26 | 12 |
| executor | 0.00 | 0% | 0.00 | 0 | 0 |
| result_verifier | 1.09 | 12% | 0.62 | 176 | 22 |
| response_generator | 1.56 | 17% | 0.61 | 339 | 29 |
| repair | 0.00 | 0% | 0.00 | 0 | 0 |
| schema_retry | 0.00 | 0% | 0.00 | 0 | 0 |

Milestone 2 traces logged only end-to-end latency, so 'before' has no per-step split.
