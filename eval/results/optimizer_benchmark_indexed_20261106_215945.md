# Optimizer benchmark (PRELIMINARY: optimizer-only, Spider dev gold SQL, small subset)

Databases: flight_2, world_1, wta_1. FK indexes added to copies: True. 1 warm-up + 5 runs, median; time limit 30.0s.

| Metric | Value |
| --- | --- |
| queries_considered | 30 |
| queries_rewritten | 2 |
| equality_maintained | 2/2 |
| plan_improved | 0/2 |
| median_ms_before_rewritten | 7.25 |
| median_ms_after_rewritten | 7.44 |
| llm_calls | 4 |
