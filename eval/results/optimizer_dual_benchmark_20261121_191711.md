# Optimizer Benchmark Report (Dual-Database Scale Evaluation)

**Suite:** CONTROLLED_DEVELOPMENT_SUITE: R5.3 scenario validation suite (not the frozen live system evaluation)

**Protocol:** 1 warm-up + 5 runs, interleaved; timeout 30.0s

- **Small DB:** `/Users/ushnesha/NextDrive/Documents/Academic/sem_3/Agentic AI/queryMind/data/analytics.db`
- **Large DB:** `/Users/ushnesha/NextDrive/Documents/Academic/sem_3/Agentic AI/queryMind/data/large_analytics.db`

## Summary Metrics

| Metric | Value |
|---|---|
| Queries Considered | 10 |
| Triggers Fired | 8 |
| Rewrites Proposed | 9 |
| Optimizer Accepted | 2 |
| Report Certified (Dual-DB Validated) | 2 |
| Dual-DB Equality Rate | 2/2 |
| Large DB Plan Improvement Rate | 2/2 |
| Large DB Median Speedup (Certified) | 2.06x |
| Large DB Median ms Before (Certified) | 7.19 ms |
| Large DB Median ms After (Certified) | 3.5 ms |

## Rejection Breakdown

| Rejection Category | Count |
|---|---|
| already_optimal_skipped | 2 |
| distinct_guard_rejected | 2 |
| equality_gate_rejected | 2 |
| plan_unimproved_rejected | 2 |

## Query Results

| ID | Category | Optimizer | Dual-Cert | Small DB Before->After (ms) | Large DB Before->After (ms) | Large DB Speedup |
|---|---|---|---|---|---|---|
| OPT01 | correlated_subquery | KEPT | KEPT | 0.15 -> 0.15 | 530.15 -> 530.15 | 1.00x |
| OPT02 | scan_consolidation | ACCEPTED | PASS | 0.14 -> 0.12 | 6.45 -> 3.08 | 2.10x |
| OPT03 | union_consolidation | ACCEPTED | PASS | 0.14 -> 0.13 | 7.92 -> 3.92 | 2.02x |
| OPT04 | distinct_unsafe_non_key | KEPT | KEPT | 0.11 -> 0.11 | 7.92 -> 7.92 | 1.00x |
| OPT05 | distinct_unsafe_join | KEPT | KEPT | 0.13 -> 0.13 | 3.98 -> 3.98 | 1.00x |
| OPT06 | distinct_safe_key | KEPT | KEPT | 0.12 -> 0.12 | 0.51 -> 0.51 | 1.00x |
| OPT07 | already_optimal | KEPT | KEPT | 0.13 -> 0.13 | 0.14 -> 0.14 | 1.00x |
| OPT08 | equality_rejection | KEPT | KEPT | 0.12 -> 0.12 | 7.20 -> 7.20 | 1.00x |
| OPT09 | in_subquery_unimproved | KEPT | KEPT | 0.13 -> 0.13 | 4.08 -> 4.08 | 1.00x |
| OPT10 | scale_timeout | KEPT | KEPT | 0.14 -> 0.14 | timeout -> timeout | 1.00x |
