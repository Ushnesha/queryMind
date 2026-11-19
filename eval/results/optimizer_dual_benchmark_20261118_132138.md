# Optimizer Benchmark Report (Dual-Database Scale Evaluation)

**Suite:** CONTROLLED_DEVELOPMENT_SUITE: R5.3 scenario validation suite (not the frozen live system evaluation)

**Protocol:** 1 warm-up + 5 runs, interleaved; timeout 30.0s

- **Small DB:** `data/analytics.db`
- **Large DB:** `data/large_analytics.db`

## Summary Metrics

| Metric | Value |
|---|---|
| Queries Considered | 10 |
| Triggers Fired | 8 |
| Rewrites Proposed | 9 |
| Optimizer Accepted | 4 |
| Report Certified (Dual-DB Validated) | 4 |
| Dual-DB Equality Rate | 4/4 |
| Large DB Plan Improvement Rate | 4/4 |
| Large DB Median Speedup (Certified) | 5.61x |
| Large DB Median ms Before (Certified) | 134.12 ms |
| Large DB Median ms After (Certified) | 15.28 ms |

## Rejection Breakdown

| Rejection Category | Count |
|---|---|
| already_optimal_skipped | 2 |
| distinct_guard_rejected | 2 |
| equality_gate_rejected | 1 |
| plan_unimproved_rejected | 1 |

## Query Results

| ID | Category | Optimizer | Dual-Cert | Small DB Before->After (ms) | Large DB Before->After (ms) | Large DB Speedup |
|---|---|---|---|---|---|---|
| OPT01 | correlated_subquery | ACCEPTED | PASS | 0.10 -> 0.10 | 264.23 -> 28.51 | 9.27x |
| OPT02 | scan_consolidation | ACCEPTED | PASS | 0.10 -> 0.09 | 3.31 -> 1.72 | 1.93x |
| OPT03 | union_consolidation | ACCEPTED | PASS | 0.10 -> 0.09 | 4.00 -> 2.06 | 1.95x |
| OPT04 | distinct_unsafe_non_key | KEPT | KEPT | 0.09 -> 0.09 | 5.11 -> 5.11 | 1.00x |
| OPT05 | distinct_unsafe_join | KEPT | KEPT | 0.10 -> 0.10 | 2.10 -> 2.10 | 1.00x |
| OPT06 | distinct_safe_key | KEPT | KEPT | 0.09 -> 0.09 | 0.36 -> 0.36 | 1.00x |
| OPT07 | already_optimal | KEPT | KEPT | 0.09 -> 0.09 | 0.09 -> 0.09 | 1.00x |
| OPT08 | equality_rejection | KEPT | KEPT | 0.10 -> 0.10 | 4.11 -> 4.11 | 1.00x |
| OPT09 | in_subquery_unimproved | KEPT | KEPT | 0.10 -> 0.10 | 2.07 -> 2.07 | 1.00x |
| OPT10 | scale_timeout | ACCEPTED | PASS | 0.10 -> 0.11 | 21841.45 -> 41.49 | 526.45x |
