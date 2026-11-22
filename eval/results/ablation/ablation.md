# R3 live ablation

## Ablation: stakeholder60

Each column switches one component off relative to the full pipeline. Cells: rate on r1 with 95% Wilson CI; below it, the change vs full in percentage points with a Newcombe 95% CI. Arrows mark the better direction.

| Metric | Full QueryMind | - Neo4j retrieval (flat schema) | - Semantic verifier | - Result verifier | - Optimizer | - Flat-schema retry |
|---|---:|---:|---:|---:|---:|---:|
| Correct, all questions ↑ | 39/50 (78%; CI 65–87) | 36/50 (72%; CI 58–83) | 31/50 (62%; CI 48–74) | 39/50 (78%; CI 65–87) | 37/50 (74%; CI 60–84) | 39/50 (78%; CI 65–87) |
| &nbsp;&nbsp;Δ vs full | — | -6 pp [-22, +11] | -16 pp [-33, +2] | +0 pp [-16, +16] | -4 pp [-20, +13] | +0 pp [-16, +16] |
| Easy accuracy ↑ | 12/13 (92%; CI 67–99) | 12/13 (92%; CI 67–99) | 12/13 (92%; CI 67–99) | 12/13 (92%; CI 67–99) | 12/13 (92%; CI 67–99) | 12/13 (92%; CI 67–99) |
| &nbsp;&nbsp;Δ vs full | — | +0 pp [-26, +26] | +0 pp [-26, +26] | +0 pp [-26, +26] | +0 pp [-26, +26] | +0 pp [-26, +26] |
| Hard accuracy ↑ | 10/17 (59%; CI 36–78) | 7/17 (41%; CI 22–64) | 6/17 (35%; CI 17–59) | 10/17 (59%; CI 36–78) | 8/17 (47%; CI 26–69) | 10/17 (59%; CI 36–78) |
| &nbsp;&nbsp;Δ vs full | — | -18 pp [-45, +15] | -24 pp [-50, +9] | +0 pp [-30, +30] | -12 pp [-40, +20] | +0 pp [-30, +30] |
| Unanswerable refused + field named ↑ | 14/14 (100%; CI 78–100) | 14/14 (100%; CI 78–100) | 14/14 (100%; CI 78–100) | 14/14 (100%; CI 78–100) | 14/14 (100%; CI 78–100) | 14/14 (100%; CI 78–100) |
| &nbsp;&nbsp;Δ vs full | — | +0 pp [-22, +22] | +0 pp [-22, +22] | +0 pp [-22, +22] | +0 pp [-22, +22] | +0 pp [-22, +22] |
| Fabrications on unanswerable ↓ | 0/14 (0%; CI 0–22) | 0/14 (0%; CI 0–22) | 0/14 (0%; CI 0–22) | 0/14 (0%; CI 0–22) | 0/14 (0%; CI 0–22) | 0/14 (0%; CI 0–22) |
| &nbsp;&nbsp;Δ vs full | — | +0 pp [-22, +22] | +0 pp [-22, +22] | +0 pp [-22, +22] | +0 pp [-22, +22] | +0 pp [-22, +22] |
| Ambiguity flagged ↑ | 5/9 (56%; CI 27–81) | 5/9 (56%; CI 27–81) | 0/9 (0%; CI 0–30) | 5/9 (56%; CI 27–81) | 5/9 (56%; CI 27–81) | 5/9 (56%; CI 27–81) |
| &nbsp;&nbsp;Δ vs full | — | +0 pp [-39, +39] | -56 pp [-81, -14] | +0 pp [-39, +39] | +0 pp [-39, +39] | +0 pp [-39, +39] |
| Over-refusal ↓ | 6/36 (17%; CI 8–32) | 11/36 (31%; CI 18–47) | 7/36 (19%; CI 10–35) | 4/36 (11%; CI 4–25) | 5/36 (14%; CI 6–29) | 6/36 (17%; CI 8–32) |
| &nbsp;&nbsp;Δ vs full | — | +14 pp [-6, +32] | +3 pp [-15, +21] | -6 pp [-22, +11] | -3 pp [-20, +14] | +0 pp [-18, +18] |
| Execution success ↑ | 30/50 (60%; CI 46–72) | 25/50 (50%; CI 37–63) | 29/50 (58%; CI 44–71) | 32/50 (64%; CI 50–76) | 31/50 (62%; CI 48–74) | 30/50 (60%; CI 46–72) |
| &nbsp;&nbsp;Δ vs full | — | -10 pp [-28, +9] | -2 pp [-21, +17] | +4 pp [-15, +22] | +2 pp [-17, +20] | +0 pp [-19, +19] |
| p50 latency (s) | 7.6 | 3.6 | 4.5 | 6.2 | 8.1 | 7.9 |
| p95 latency (s) | 23.3 | 16.9 | 14.0 | 22.2 | 18.5 | 25.2 |
| LLM calls / question | 3.22 | 2.60 | 2.54 | 2.68 | 3.20 | 2.88 |
| Tokens / question | 1371 | 1095 | 1020 | 1210 | 1361 | 1203 |
| Flat-schema retries (triggered / answered) | 16 / 1 | 0 / 0 | 16 / 1 | 14 / 1 | 15 / 1 | 0 / 0 |

| Variant | Paired n | Lost vs full | Gained vs full | exact McNemar p |
|---|---:|---:|---:|---:|
| - Neo4j retrieval (flat schema) | 50 | 3 | 0 | 0.250 |
| - Semantic verifier | 50 | 8 | 0 | 0.008 |
| - Result verifier | 50 | 1 | 1 | 1.000 |
| - Optimizer | 50 | 2 | 0 | 0.500 |
| - Flat-schema retry | 50 | 1 | 1 | 1.000 |
