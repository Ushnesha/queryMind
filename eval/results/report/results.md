# Report evaluation results

## stakeholder

| Metric | b0 (frozen single call) | b1 (b0 + refusal sentence) | QueryMind (Neo4j schema) | QueryMind, flat schema (diagnostic) |
|---|---:|---:|---:|---:|
| Easy accuracy (set easy) | 5/5 (100%; CI 57–100) | 5/5 (100%; CI 57–100) | 3/5 (60%; CI 23–88) | 4/5 (80%; CI 38–96) |
| Hard accuracy (set hard) | 0/5 (0%; CI 0–43) | 1/5 (20%; CI 4–62) | 2/5 (40%; CI 12–77) | 2/5 (40%; CI 12–77) |
| Unanswerable refused + field named | 0/6 (0%; CI 0–39) | 6/6 (100%; CI 61–100) | 6/6 (100%; CI 61–100) | 6/6 (100%; CI 61–100) |
| Fabrications on unanswerable (lower is better) | 5/6 (83%; CI 44–97) | 0/6 (0%; CI 0–39) | 0/6 (0%; CI 0–39) | 0/6 (0%; CI 0–39) |
| Ambiguity flagged (assumption stated) | 0/4 (0%; CI 0–49) | 0/4 (0%; CI 0–49) | 2/4 (50%; CI 15–85) | 2/4 (50%; CI 15–85) |
| Assumptions stated on unambiguous reference questions | 0/7 (0%; CI 0–35) | 0/7 (0%; CI 0–35) | 3/7 (43%; CI 16–75) | 5/7 (71%; CI 36–92) |
| Over-refusal (refused an answerable question) | 0/11 (0%; CI 0–26) | 2/11 (18%; CI 5–48) | 6/11 (55%; CI 28–79) | 3/11 (27%; CI 10–57) |
| Execution success (all questions) | 15/17 (88%; CI 66–97) | 9/17 (53%; CI 31–74) | 5/17 (29%; CI 13–53) | 8/17 (47%; CI 26–69) |
| Execution success when an answer was attempted | 15/17 (88%; CI 66–97) | 9/9 (100%; CI 70–100) | 5/5 (100%; CI 57–100) | 8/8 (100%; CI 68–100) |
| Write attempts in generated SQL | 0 | 0 | 0 | 0 |
| p50 / p95 end-to-end latency (s) | 3.80 / 17.10 | 1.23 / 11.35 | 0.91 / 35.74 | 0.90 / 36.65 |
| p50 latency, answered questions only (s) | 3.80 | 3.26 | 12.02 | 11.88 |
| Questions over 15 s | 1/17 | 0/17 | 2/17 | 2/17 |
| LLM calls / question (mean) | 1.00 | 1.00 | 2.00 | 2.47 |
| Tokens / question (prompt+completion, mean) | 346 | 316 | 739 | 984 |
| Gateway errors remaining after retries | 0 | 0 | 0 | 0 |

Rates are run r1 with 95% Wilson intervals (stakeholder `score.wilson`).

### Repeat stability

| Arm | r1 correct (all kinds) | r2 correct (all kinds) | r3 correct (all kinds) | Same verdict in every run |
|---|---:|---:|---:|---:|
| b0 (frozen single call) | 5/17 | 5/17 | 5/17 | 17/17 |
| b1 (b0 + refusal sentence) | 11/17 | 11/17 | 11/17 | 17/17 |
| QueryMind (Neo4j schema) | 11/17 | 11/17 | 11/17 | 17/17 |
| QueryMind, flat schema (diagnostic) | 12/17 | 0/0 | 0/0 | N/A |

### Paired comparison on r1 (exact McNemar, all scored questions)

| Pair (A vs B) | Questions | Only A correct | Only B correct | p |
|---|---:|---:|---:|---:|
| b0 vs b1 | 17 | 0 | 6 | 0.031 |
| querymind vs b1 | 17 | 2 | 2 | 1.000 |
| querymind-flat vs b1 | 17 | 2 | 1 | 1.000 |
| querymind vs b0 | 17 | 8 | 2 | 0.109 |
| querymind vs querymind-flat | 17 | 0 | 1 | 1.000 |

### Per-question verdicts (r1)

| Question | Set | Kind | b0 | b1 | querymind | querymind-flat |
|---|---|---|---|---|---|---|
| A1 | ambiguous | ambiguous | FAIL: silently chose one interpretation | FAIL: silently chose one interpretation | PASS: stated assumptions | PASS: stated assumptions |
| A2 | ambiguous | ambiguous | FAIL: silently chose one interpretation | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| E1 | easy | reference | PASS: matches reference: columns [1, 2] (order enforced) | PASS: matches reference: columns [1, 2] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) |
| E2 | easy | reference | PASS: matches reference: columns [0, 1] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) | FAIL: refused an answerable question (over-refusal) | FAIL: mismatch: 1 columns cannot cover reference's 2 |
| E3 | easy | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | FAIL: refused an answerable question (over-refusal) | PASS: matches reference: columns [0, 1] (unordered) |
| E4 | easy | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| E5 | easy | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| H1 | hard | ambiguous | FAIL: silently chose one interpretation | FAIL: silently chose one interpretation | PASS: stated assumptions | PASS: stated assumptions |
| H2 | hard | ambiguous | FAIL: silently chose one interpretation | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| H3 | hard | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'cost or profit data' | PASS: refused, named '<cost or revenue information>' | PASS: refused, named '<cost information>' |
| H4 | hard | reference | FAIL: execution failed: OperationalError | FAIL: mismatch: 2 columns cannot cover reference's 3 | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| H5 | hard | reference | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: refused an answerable question (over-refusal) | FAIL: mismatch: no column mapping reproduces the reference rows |
| U1 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'sales representative' | PASS: refused, named '<sales representative>' | PASS: refused, named '<sales representative>' |
| U2 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'churn data' | PASS: refused, named 'churn information' | PASS: refused, named '<churn information>' |
| U3 | unanswerable | unanswerable | FAIL: no refusal and no result | PASS: refused, named 'marketing channel' | PASS: refused, named 'marketing channel' | PASS: refused, named '<marketing channel>' |
| U4 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'stock quantity or inventory information' | PASS: refused, named 'stock quantity' | PASS: refused, named '<stock quantity>' |
| U5 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'delivery time or related date fields' | PASS: refused, named 'delivery time' | PASS: refused, named '<delivery time>' |

### QueryMind (Neo4j schema) behaviour (all runs)

```json
{
  "runs": 51,
  "first_attempt_verification_failures": 3,
  "runs_with_repairs": 0,
  "repairs_recovered_to_execution": 0,
  "repairs_recovered_correct": 0,
  "error_types": {},
  "optimizer_invoked": 15,
  "optimizer_rewrites_applied": 3,
  "optimizer_rewrites_result_equal": 3,
  "schema_backend": {
    "neo4j": 51
  },
  "semantic_judge_unavailable": 0,
  "llm_calls_distribution": {
    "1": 33,
    "2": 3,
    "4": 12,
    "5": 3
  },
  "calls_without_token_usage": 0
}
```

### QueryMind, flat schema (diagnostic) behaviour (all runs)

```json
{
  "runs": 17,
  "first_attempt_verification_failures": 0,
  "runs_with_repairs": 0,
  "repairs_recovered_to_execution": 0,
  "repairs_recovered_correct": 0,
  "error_types": {},
  "optimizer_invoked": 8,
  "optimizer_rewrites_applied": 1,
  "optimizer_rewrites_result_equal": 1,
  "schema_backend": {
    "flat": 17
  },
  "semantic_judge_unavailable": 0,
  "llm_calls_distribution": {
    "1": 9,
    "4": 7,
    "5": 1
  },
  "calls_without_token_usage": 0
}
```

## stakeholder60

| Metric | b0 (frozen single call) | b1 (b0 + refusal sentence) | b2 (k=3 samples, result vote) | QueryMind (Neo4j schema) | QueryMind, flat schema (diagnostic) |
|---|---:|---:|---:|---:|---:|
| Easy accuracy (set easy) | 13/13 (100%; CI 77–100) | 12/13 (92%; CI 67–99) | 12/13 (92%; CI 67–99) | 12/13 (92%; CI 67–99) | 12/13 (92%; CI 67–99) |
| Hard accuracy (set hard) | 7/17 (41%; CI 22–64) | 9/17 (53%; CI 31–74) | 5/17 (29%; CI 13–53) | 10/17 (59%; CI 36–78) | 7/17 (41%; CI 22–64) |
| Unanswerable refused + field named | 0/14 (0%; CI 0–22) | 14/14 (100%; CI 78–100) | 12/14 (86%; CI 60–96) | 14/14 (100%; CI 78–100) | 14/14 (100%; CI 78–100) |
| Fabrications on unanswerable (lower is better) | 10/14 (71%; CI 45–88) | 0/14 (0%; CI 0–22) | 0/14 (0%; CI 0–22) | 0/14 (0%; CI 0–22) | 0/14 (0%; CI 0–22) |
| Ambiguity flagged (assumption stated) | 0/9 (0%; CI 0–30) | 0/9 (0%; CI 0–30) | 0/9 (0%; CI 0–30) | 5/9 (56%; CI 27–81) | 5/9 (56%; CI 27–81) |
| Assumptions stated on unambiguous reference questions | 0/27 (0%; CI 0–12) | 0/27 (0%; CI 0–12) | 0/27 (0%; CI 0–12) | 19/27 (70%; CI 52–84) | 14/27 (52%; CI 34–69) |
| Over-refusal (refused an answerable question) | 0/36 (0%; CI 0–10) | 1/36 (3%; CI 0–14) | 18/36 (50%; CI 34–66) | 6/36 (17%; CI 8–32) | 11/36 (31%; CI 18–47) |
| Execution success (all questions) | 45/50 (90%; CI 79–96) | 35/50 (70%; CI 56–81) | 18/50 (36%; CI 24–50) | 30/50 (60%; CI 46–72) | 25/50 (50%; CI 37–63) |
| Execution success when an answer was attempted | 45/50 (90%; CI 79–96) | 35/35 (100%; CI 90–100) | 18/18 (100%; CI 82–100) | 30/30 (100%; CI 89–100) | 25/25 (100%; CI 87–100) |
| Write attempts in generated SQL | 0 | 0 | 0 | 0 | 0 |
| p50 / p95 end-to-end latency (s) | 4.23 / 12.66 | 2.67 / 9.83 | 4.62 / 15.26 | 7.62 / 23.34 | 3.57 / 16.92 |
| p50 latency, answered questions only (s) | 4.12 | 4.22 | 6.10 | 11.87 | 9.97 |
| Questions over 15 s | 1/50 | 0/50 | 3/50 | 9/50 | 6/50 |
| LLM calls / question (mean) | 1.00 | 1.00 | 3.00 | 3.22 | 2.60 |
| Tokens / question (prompt+completion, mean) | 328 | 339 | 1138 | 1371 | 1095 |
| Gateway errors remaining after retries | 0 | 0 | 0 | 0 | 0 |

Rates are run r1 with 95% Wilson intervals (stakeholder `score.wilson`).

### Repeat stability

| Arm | r1 correct (all kinds) | r2 correct (all kinds) | r3 correct (all kinds) | Same verdict in every run |
|---|---:|---:|---:|---:|
| b0 (frozen single call) | 20/50 | 20/50 | 20/50 | 50/50 |
| b1 (b0 + refusal sentence) | 34/50 | 34/50 | 34/50 | 50/50 |
| b2 (k=3 samples, result vote) | 29/50 | 24/50 | 25/50 | 40/50 |
| QueryMind (Neo4j schema) | 39/50 | 37/50 | 39/50 | 46/50 |
| QueryMind, flat schema (diagnostic) | 36/50 | 36/50 | 36/50 | 50/50 |

### Paired comparison on r1 (exact McNemar, all scored questions)

| Pair (A vs B) | Questions | Only A correct | Only B correct | p |
|---|---:|---:|---:|---:|
| b0 vs b1 | 50 | 1 | 15 | 0.001 |
| b2 vs b1 | 50 | 1 | 6 | 0.125 |
| querymind vs b1 | 50 | 7 | 2 | 0.180 |
| querymind-flat vs b1 | 50 | 6 | 4 | 0.754 |
| querymind vs b0 | 50 | 21 | 2 | 0.000 |
| querymind vs b2 | 50 | 10 | 0 | 0.002 |
| querymind vs querymind-flat | 50 | 3 | 0 | 0.250 |

### Per-question verdicts (r1)

| Question | Set | Kind | b0 | b1 | b2 | querymind | querymind-flat |
|---|---|---|---|---|---|---|---|
| A1 | ambiguous | ambiguous | FAIL: silently chose one interpretation | FAIL: silently chose one interpretation | FAIL: refused an answerable question (over-refusal) | PASS: stated assumptions | PASS: stated assumptions |
| A2 | ambiguous | ambiguous | FAIL: silently chose one interpretation | FAIL: silently chose one interpretation | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| E1 | easy | reference | PASS: matches reference: columns [1, 2] (order enforced) | PASS: matches reference: columns [1, 2] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) |
| E2 | easy | reference | PASS: matches reference: columns [0, 1] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) | FAIL: refused an answerable question (over-refusal) | FAIL: mismatch: 1 columns cannot cover reference's 2 | FAIL: mismatch: 1 columns cannot cover reference's 2 |
| E3 | easy | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| E4 | easy | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| E5 | easy | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| H1 | hard | ambiguous | FAIL: silently chose one interpretation | FAIL: silently chose one interpretation | FAIL: refused an answerable question (over-refusal) | PASS: stated assumptions | PASS: stated assumptions |
| H2 | hard | ambiguous | FAIL: silently chose one interpretation | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| H3 | hard | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'cost or profit information' | FAIL: refused but named 'None' | PASS: refused, named '<cost information>' | PASS: refused, named '<cost information>' |
| H4 | hard | reference | FAIL: execution failed: OperationalError | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| H5 | hard | reference | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: refused an answerable question (over-refusal) | PASS: matches reference: columns [2, 0, 3] (unordered) | FAIL: refused an answerable question (over-refusal) |
| M1-A1 | ambiguous | ambiguous | FAIL: silently chose one interpretation | FAIL: silently chose one interpretation | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| M1-A2 | ambiguous | ambiguous | FAIL: silently chose one interpretation | FAIL: silently chose one interpretation | FAIL: refused an answerable question (over-refusal) | PASS: stated assumptions | PASS: stated assumptions |
| M1-E1 | easy | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| M1-E2 | easy | reference | PASS: matches reference: columns [0, 1] (unordered) | FAIL: mismatch: 1 columns cannot cover reference's 2 | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| M1-H1 | hard | reference | PASS: matches reference: columns [0, 2] (unordered) | PASS: matches reference: columns [0, 2] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | FAIL: mismatch: no column mapping reproduces the reference rows |
| M1-H2 | hard | reference | PASS: matches reference: columns [1] (unordered) | PASS: matches reference: columns [1] (unordered) | FAIL: refused an answerable question (over-refusal) | PASS: matches reference: columns [1] (unordered) | PASS: matches reference: columns [1] (unordered) |
| M1-H3 | hard | reference | PASS: matches reference: columns [1] (unordered) | PASS: matches reference: columns [1] (unordered) | PASS: matches reference: columns [1] (unordered) | PASS: matches reference: columns [1] (unordered) | PASS: matches reference: columns [1] (unordered) |
| M1-U1 | unanswerable | unanswerable | FAIL: no refusal and no result | PASS: refused, named 'payment_method' | PASS: refused, named '<payment method>' | PASS: refused, named '<payment method>' | PASS: refused, named '<payment method>' |
| M1-U2 | unanswerable | unanswerable | FAIL: no refusal and no result | PASS: refused, named 'returns table' | PASS: refused, named '<return information>' | PASS: refused, named 'return information' | PASS: refused, named '<return information>' |
| M2-A1 | ambiguous | ambiguous | FAIL: silently chose one interpretation | FAIL: silently chose one interpretation | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| M2-E1 | easy | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| M2-E2 | easy | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| M2-H1 | hard | reference | FAIL: mismatch: row count 11 != reference 12 | FAIL: mismatch: row count 11 != reference 12 | FAIL: refused an answerable question (over-refusal) | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: refused an answerable question (over-refusal) |
| M2-H2 | hard | reference | FAIL: mismatch: row count 1 != reference 4 | FAIL: mismatch: row count 1 != reference 4 | FAIL: refused an answerable question (over-refusal) | FAIL: mismatch: row count 1 != reference 4 | FAIL: refused an answerable question (over-refusal) |
| M2-H3 | hard | reference | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: refused an answerable question (over-refusal) | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: mismatch: no column mapping reproduces the reference rows |
| M2-U1 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'customer rating' | FAIL: refused but named 'None' | PASS: refused, named '<rating>' | PASS: refused, named '<rating>' |
| M2-U2 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'customer age' | PASS: refused, named '<age>' | PASS: refused, named '<age>' | PASS: refused, named '<age>' |
| M3-A1 | ambiguous | ambiguous | FAIL: silently chose one interpretation | FAIL: silently chose one interpretation | FAIL: refused an answerable question (over-refusal) | PASS: stated assumptions | PASS: stated assumptions |
| M3-E1 | easy | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| M3-E2 | easy | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| M3-H1 | hard | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| M3-H2 | hard | reference | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: refused an answerable question (over-refusal) | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: refused an answerable question (over-refusal) |
| M3-H3 | hard | reference | FAIL: mismatch: row count 20 != reference 8 | PASS: matches reference: columns [1] (unordered) | FAIL: refused an answerable question (over-refusal) | PASS: matches reference: columns [1] (unordered) | FAIL: refused an answerable question (over-refusal) |
| M3-U1 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'shipping cost' | PASS: refused, named 'shipping cost' | PASS: refused, named 'shipping cost' | PASS: refused, named 'shipping cost' |
| M3-U2 | unanswerable | unanswerable | FAIL: no refusal and no result | PASS: refused, named 'discount codes' | PASS: refused, named '<discount codes>' | PASS: refused, named '<discount codes>' | PASS: refused, named '<discount codes>' |
| M4-A1 | ambiguous | ambiguous | FAIL: silently chose one interpretation | FAIL: silently chose one interpretation | FAIL: silently chose one interpretation | PASS: stated assumptions | PASS: stated assumptions |
| M4-E1 | easy | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| M4-E2 | easy | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| M4-H1 | hard | reference | PASS: matches reference: columns [2, 1] (unordered) | PASS: matches reference: columns [2, 1] (unordered) | PASS: matches reference: columns [1, 0] (unordered) | PASS: matches reference: columns [1, 0] (unordered) | PASS: matches reference: columns [1, 0] (unordered) |
| M4-H2 | hard | reference | PASS: matches reference: columns [0, 2] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) | PASS: matches reference: columns [0, 2] (order enforced) | PASS: matches reference: columns [0, 2] (order enforced) | PASS: matches reference: columns [0, 2] (order enforced) |
| M4-H3 | hard | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| M4-U1 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'shipping_cost' | PASS: refused, named 'shipping_cost' | PASS: refused, named 'shipping cost' | PASS: refused, named 'shipping cost' |
| M4-U2 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'discount information' | PASS: refused, named '<discount>' | PASS: refused, named '<discount>' | PASS: refused, named '<discount>' |
| U1 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'sales representative' | PASS: refused, named '<sales representative>' | PASS: refused, named '<sales representative>' | PASS: refused, named '<sales representative>' |
| U2 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'churn data' | PASS: refused, named 'churn information' | PASS: refused, named 'churn information' | PASS: refused, named '<churn information>' |
| U3 | unanswerable | unanswerable | FAIL: no refusal and no result | PASS: refused, named 'marketing channel' | PASS: refused, named '<marketing channel>' | PASS: refused, named 'marketing channel' | PASS: refused, named '<marketing channel>' |
| U4 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'stock quantity or inventory information' | PASS: refused, named '<inventory quantity>' | PASS: refused, named '<stock quantity>' | PASS: refused, named '<stock quantity>' |
| U5 | unanswerable | unanswerable | FAIL: FABRICATED: returned a result set for missing data | PASS: refused, named 'delivery time or related date fields' | PASS: refused, named '<delivery time>' | PASS: refused, named '<delivery time>' | PASS: refused, named '<delivery time>' |

### QueryMind (Neo4j schema) behaviour (all runs)

```json
{
  "runs": 150,
  "first_attempt_verification_failures": 3,
  "runs_with_repairs": 3,
  "repairs_recovered_to_execution": 3,
  "repairs_recovered_correct": 3,
  "error_types": {},
  "optimizer_invoked": 93,
  "optimizer_rewrites_applied": 2,
  "optimizer_rewrites_result_equal": 2,
  "schema_backend": {
    "neo4j": 150
  },
  "semantic_judge_unavailable": 0,
  "llm_calls_distribution": {
    "1": 16,
    "2": 41,
    "4": 78,
    "5": 12,
    "7": 3
  },
  "calls_without_token_usage": 0
}
```

### QueryMind, flat schema (diagnostic) behaviour (all runs)

```json
{
  "runs": 150,
  "first_attempt_verification_failures": 5,
  "runs_with_repairs": 5,
  "repairs_recovered_to_execution": 5,
  "repairs_recovered_correct": 5,
  "error_types": {},
  "optimizer_invoked": 78,
  "optimizer_rewrites_applied": 0,
  "optimizer_rewrites_result_equal": 0,
  "schema_backend": {
    "flat": 150
  },
  "semantic_judge_unavailable": 0,
  "llm_calls_distribution": {
    "1": 72,
    "4": 67,
    "5": 6,
    "7": 5
  },
  "calls_without_token_usage": 0
}
```

## spider

| Metric | b0 (frozen single call) | b1 (b0 + refusal sentence) | QueryMind (Neo4j schema) | QueryMind, flat schema (diagnostic) |
|---|---:|---:|---:|---:|
| Execution accuracy, all | 39/50 (78%; CI 65–87) | 37/50 (74%; CI 60–84) | 33/50 (66%; CI 52–78) | 36/50 (72%; CI 58–83) |
| Execution accuracy, single-table | 23/25 (92%; CI 75–98) | 23/25 (92%; CI 75–98) | 23/25 (92%; CI 75–98) | 23/25 (92%; CI 75–98) |
| Execution accuracy, multi-table/nested | 16/25 (64%; CI 45–80) | 14/25 (56%; CI 37–73) | 10/25 (40%; CI 23–59) | 13/25 (52%; CI 33–70) |
| Over-refusal (refused an answerable question) | 0/50 (0%; CI 0–7) | 2/50 (4%; CI 1–13) | 9/50 (18%; CI 10–31) | 6/50 (12%; CI 6–24) |
| Execution success (all questions) | 49/50 (98%; CI 90–100) | 47/50 (94%; CI 84–98) | 41/50 (82%; CI 69–90) | 44/50 (88%; CI 76–94) |
| Execution success when an answer was attempted | 49/50 (98%; CI 90–100) | 47/48 (98%; CI 89–100) | 41/41 (100%; CI 91–100) | 44/44 (100%; CI 92–100) |
| Write attempts in generated SQL | 0 | 0 | 0 | 0 |
| p50 / p95 end-to-end latency (s) | 2.25 / 4.97 | 2.22 / 4.22 | 8.47 / 21.47 | 8.70 / 19.05 |
| p50 latency, answered questions only (s) | 2.25 | 2.23 | 9.24 | 9.26 |
| Questions over 15 s | 0/50 | 0/50 | 6/50 | 8/50 |
| LLM calls / question (mean) | 1.00 | 1.00 | 3.70 | 3.90 |
| Tokens / question (prompt+completion, mean) | 371 | 413 | 1290 | 1671 |
| Gateway errors remaining after retries | 0 | 0 | 0 | 0 |

Rates are run r1 with 95% Wilson intervals (stakeholder `score.wilson`).

### Paired comparison on r1 (exact McNemar, all scored questions)

| Pair (A vs B) | Questions | Only A correct | Only B correct | p |
|---|---:|---:|---:|---:|
| b0 vs b1 | 50 | 2 | 0 | 0.500 |
| querymind vs b1 | 50 | 0 | 4 | 0.125 |
| querymind-flat vs b1 | 50 | 1 | 2 | 1.000 |
| querymind vs b0 | 50 | 0 | 6 | 0.031 |
| querymind vs querymind-flat | 50 | 1 | 4 | 0.375 |

### Per-question verdicts (r1)

| Question | Set | Kind | b0 | b1 | querymind | querymind-flat |
|---|---|---|---|---|---|---|
| S0493 (battle_death) | single | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| S0499 (battle_death) | multi | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| S0506 (battle_death) | single | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0099 (car_1) | multi | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | FAIL: mismatch: row count 22 != reference 11 | PASS: matches reference: columns [0] (unordered) |
| S0102 (car_1) | multi | reference | FAIL: mismatch: row count 1 != reference 35 | FAIL: mismatch: row count 1 != reference 35 | FAIL: mismatch: row count 1 != reference 35 | FAIL: mismatch: row count 1 != reference 35 |
| S0035 (concert_singer) | multi | reference | FAIL: mismatch: row count 6 != reference 5 | FAIL: mismatch: row count 6 != reference 5 | FAIL: mismatch: row count 6 != reference 5 | FAIL: mismatch: row count 6 != reference 5 |
| S0381 (course_teach) | single | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0384 (course_teach) | single | reference | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) |
| S0390 (course_teach) | single | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0304 (cre_Doc_Template_Mgt) | single | reference | PASS: matches reference: columns [0, 1, 2] (unordered) | PASS: matches reference: columns [0, 1, 2] (unordered) | PASS: matches reference: columns [0, 1, 2] (unordered) | PASS: matches reference: columns [0, 1, 2] (unordered) |
| S0319 (cre_Doc_Template_Mgt) | single | reference | PASS: matches reference: columns [0, 1, 2] (unordered) | PASS: matches reference: columns [0, 1, 2] (unordered) | PASS: matches reference: columns [0, 1, 2] (unordered) | PASS: matches reference: columns [0, 1, 2] (unordered) |
| S0328 (cre_Doc_Template_Mgt) | single | reference | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) | PASS: matches reference: columns [0, 1] (unordered) |
| S0331 (cre_Doc_Template_Mgt) | single | reference | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) |
| S0359 (cre_Doc_Template_Mgt) | multi | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0361 (cre_Doc_Template_Mgt) | single | reference | FAIL: mismatch: row count 0 != reference 2 | FAIL: mismatch: row count 0 != reference 2 | FAIL: mismatch: row count 0 != reference 2 | FAIL: mismatch: row count 0 != reference 2 |
| S0376 (cre_Doc_Template_Mgt) | single | reference | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) |
| S0943 (dog_kennels) | multi | reference | FAIL: mismatch: row count 4 != reference 6 | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| S0993 (dog_kennels) | single | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0995 (dog_kennels) | single | reference | PASS: matches reference: columns [0, 1, 2] (unordered) | PASS: matches reference: columns [0, 1, 2] (unordered) | PASS: matches reference: columns [0, 1, 2] (unordered) | PASS: matches reference: columns [0, 1, 2] (unordered) |
| S0261 (employee_hire_evaluation) | single | reference | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) |
| S0210 (flight_2) | multi | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0211 (flight_2) | multi | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | FAIL: refused an answerable question (over-refusal) |
| S0214 (flight_2) | multi | reference | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: refused an answerable question (over-refusal) | FAIL: mismatch: no column mapping reproduces the reference rows |
| S0220 (flight_2) | multi | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0231 (flight_2) | multi | reference | PASS: matches reference: columns [0, 1] (order enforced) | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: mismatch: no column mapping reproduces the reference rows |
| S0889 (network_1) | multi | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | FAIL: refused an answerable question (over-refusal) | PASS: matches reference: columns [0] (unordered) |
| S0892 (network_1) | multi | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | FAIL: refused an answerable question (over-refusal) | PASS: matches reference: columns [0] (unordered) |
| S0846 (orchestra) | multi | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0648 (poker_player) | single | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0654 (poker_player) | single | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S1023 (singer) | multi | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0537 (student_transcripts_tracking) | multi | reference | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: mismatch: no column mapping reproduces the reference rows | FAIL: refused an answerable question (over-refusal) | PASS: matches reference: columns [0] (order enforced) |
| S0561 (student_transcripts_tracking) | multi | reference | PASS: matches reference: columns [0, 1, 2] (order enforced) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| S0610 (tvshow) | multi | reference | FAIL: mismatch: row count 0 != reference 1 | FAIL: mismatch: row count 0 != reference 1 | FAIL: mismatch: row count 0 != reference 1 | FAIL: mismatch: row count 0 != reference 1 |
| S0629 (tvshow) | single | reference | PASS: matches reference: columns [0, 1] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) |
| S0636 (tvshow) | multi | reference | FAIL: mismatch: row count 3 != reference 1 | FAIL: mismatch: row count 3 != reference 1 | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| S0692 (voter_1) | single | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0706 (world_1) | single | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0710 (world_1) | multi | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0733 (world_1) | single | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0735 (world_1) | single | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0742 (world_1) | multi | reference | PASS: matches reference: columns [0] (order enforced) | PASS: matches reference: columns [0] (order enforced) | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| S0771 (world_1) | multi | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0774 (world_1) | multi | reference | FAIL: execution failed: OperationalError | FAIL: execution failed: OperationalError | FAIL: refused an answerable question (over-refusal) | FAIL: refused an answerable question (over-refusal) |
| S0783 (world_1) | multi | reference | FAIL: mismatch: row count 49 != reference 69 | FAIL: mismatch: row count 49 != reference 69 | FAIL: mismatch: row count 49 != reference 69 | FAIL: mismatch: row count 49 != reference 69 |
| S0795 (world_1) | multi | reference | PASS: matches reference: columns [1, 0] (unordered) | PASS: matches reference: columns [1, 0] (unordered) | PASS: matches reference: columns [1, 0] (unordered) | PASS: matches reference: columns [1, 0] (unordered) |
| S0800 (world_1) | single | reference | PASS: matches reference: columns [0, 1] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) | PASS: matches reference: columns [0, 1] (order enforced) |
| S0813 (world_1) | single | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0446 (wta_1) | single | reference | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) | PASS: matches reference: columns [0] (unordered) |
| S0458 (wta_1) | single | reference | FAIL: mismatch: 1 columns cannot cover reference's 2 | FAIL: mismatch: 1 columns cannot cover reference's 2 | FAIL: mismatch: row count 0 != reference 487 | FAIL: mismatch: 1 columns cannot cover reference's 2 |

### QueryMind (Neo4j schema) behaviour (all runs)

```json
{
  "runs": 50,
  "first_attempt_verification_failures": 1,
  "runs_with_repairs": 1,
  "repairs_recovered_to_execution": 1,
  "repairs_recovered_correct": 1,
  "error_types": {},
  "optimizer_invoked": 41,
  "optimizer_rewrites_applied": 2,
  "optimizer_rewrites_result_equal": 2,
  "schema_backend": {
    "neo4j": 50
  },
  "semantic_judge_unavailable": 0,
  "llm_calls_distribution": {
    "1": 9,
    "3": 2,
    "4": 27,
    "5": 10,
    "6": 2
  },
  "calls_without_token_usage": 0
}
```

### QueryMind, flat schema (diagnostic) behaviour (all runs)

```json
{
  "runs": 50,
  "first_attempt_verification_failures": 1,
  "runs_with_repairs": 1,
  "repairs_recovered_to_execution": 1,
  "repairs_recovered_correct": 1,
  "error_types": {},
  "optimizer_invoked": 44,
  "optimizer_rewrites_applied": 2,
  "optimizer_rewrites_result_equal": 2,
  "schema_backend": {
    "flat": 50
  },
  "semantic_judge_unavailable": 0,
  "llm_calls_distribution": {
    "1": 6,
    "3": 2,
    "4": 29,
    "5": 11,
    "6": 2
  },
  "calls_without_token_usage": 0
}
```
