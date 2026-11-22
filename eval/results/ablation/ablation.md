# R3 live ablation

## Ablation: stakeholder60

Each column switches one component off relative to the full pipeline. Cells: rate on r1 with 95% Wilson CI; below it, the change vs full in percentage points with a Newcombe 95% CI. Arrows mark the better direction.

| Metric | Full QueryMind | - Neo4j retrieval (flat schema) | - Semantic verifier | - Result verifier | - Optimizer | - Flat-schema retry |
|---|---:|---:|---:|---:|---:|---:|
| Correct, all questions ↑ | 47/60 (78%; CI 66–87) | 44/60 (73%; CI 61–83) | 38/60 (63%; CI 51–74) | 47/60 (78%; CI 66–87) | 45/60 (75%; CI 63–84) | 47/60 (78%; CI 66–87) |
| &nbsp;&nbsp;Δ vs full | — | -5 pp [-20, +10] | -15 pp [-30, +1] | +0 pp [-15, +15] | -3 pp [-18, +12] | +0 pp [-15, +15] |
| Easy accuracy ↑ | 14/15 (93%; CI 70–99) | 14/15 (93%; CI 70–99) | 14/15 (93%; CI 70–99) | 14/15 (93%; CI 70–99) | 14/15 (93%; CI 70–99) | 14/15 (93%; CI 70–99) |
| &nbsp;&nbsp;Δ vs full | — | +0 pp [-24, +24] | +0 pp [-24, +24] | +0 pp [-24, +24] | +0 pp [-24, +24] | +0 pp [-24, +24] |
| Hard accuracy ↑ | 12/20 (60%; CI 39–78) | 9/20 (45%; CI 26–66) | 9/20 (45%; CI 26–66) | 12/20 (60%; CI 39–78) | 10/20 (50%; CI 30–70) | 12/20 (60%; CI 39–78) |
| &nbsp;&nbsp;Δ vs full | — | -15 pp [-41, +15] | -15 pp [-41, +15] | +0 pp [-28, +28] | -10 pp [-37, +19] | +0 pp [-28, +28] |
| Unanswerable refused + field named ↑ | 16/16 (100%; CI 81–100) | 16/16 (100%; CI 81–100) | 16/16 (100%; CI 81–100) | 16/16 (100%; CI 81–100) | 16/16 (100%; CI 81–100) | 16/16 (100%; CI 81–100) |
| &nbsp;&nbsp;Δ vs full | — | +0 pp [-19, +19] | +0 pp [-19, +19] | +0 pp [-19, +19] | +0 pp [-19, +19] | +0 pp [-19, +19] |
| Fabrications on unanswerable ↓ | 0/16 (0%; CI 0–19) | 0/16 (0%; CI 0–19) | 0/16 (0%; CI 0–19) | 0/16 (0%; CI 0–19) | 0/16 (0%; CI 0–19) | 0/16 (0%; CI 0–19) |
| &nbsp;&nbsp;Δ vs full | — | +0 pp [-19, +19] | +0 pp [-19, +19] | +0 pp [-19, +19] | +0 pp [-19, +19] | +0 pp [-19, +19] |
| Ambiguity flagged ↑ | 7/12 (58%; CI 32–81) | 7/12 (58%; CI 32–81) | 0/12 (0%; CI 0–24) | 7/12 (58%; CI 32–81) | 7/12 (58%; CI 32–81) | 7/12 (58%; CI 32–81) |
| &nbsp;&nbsp;Δ vs full | — | +0 pp [-35, +35] | -58 pp [-81, -22] | +0 pp [-35, +35] | +0 pp [-35, +35] | +0 pp [-35, +35] |
| Over-refusal ↓ | 8/44 (18%; CI 10–32) | 13/44 (30%; CI 18–44) | 8/44 (18%; CI 10–32) | 6/44 (14%; CI 6–27) | 7/44 (16%; CI 8–29) | 8/44 (18%; CI 10–32) |
| &nbsp;&nbsp;Δ vs full | — | +11 pp [-7, +28] | +0 pp [-16, +16] | -5 pp [-20, +11] | -2 pp [-18, +14] | +0 pp [-16, +16] |
| Execution success ↑ | 36/60 (60%; CI 47–71) | 31/60 (52%; CI 39–64) | 36/60 (60%; CI 47–71) | 38/60 (63%; CI 51–74) | 37/60 (62%; CI 49–73) | 36/60 (60%; CI 47–71) |
| &nbsp;&nbsp;Δ vs full | — | -8 pp [-25, +9] | +0 pp [-17, +17] | +3 pp [-14, +20] | +2 pp [-15, +19] | +0 pp [-17, +17] |
| p50 latency (s) | 7.8 | 6.2 | 4.6 | 6.3 | 8.2 | 8.3 |
| p95 latency (s) | 23.3 | 16.9 | 13.1 | 22.2 | 18.5 | 25.2 |
| LLM calls / question | 3.33 | 2.63 | 2.57 | 2.78 | 3.32 | 2.98 |
| Tokens / question | 1419 | 1105 | 1035 | 1256 | 1410 | 1254 |
| Flat-schema retries (triggered / answered) | 20 / 1 | 0 / 0 | 19 / 1 | 18 / 1 | 19 / 1 | 0 / 0 |

| Variant | Paired n | Lost vs full | Gained vs full | exact McNemar p |
|---|---:|---:|---:|---:|
| - Neo4j retrieval (flat schema) | 60 | 3 | 0 | 0.250 |
| - Semantic verifier | 60 | 10 | 1 | 0.012 |
| - Result verifier | 60 | 1 | 1 | 1.000 |
| - Optimizer | 60 | 2 | 0 | 0.500 |
| - Flat-schema retry | 60 | 1 | 1 | 1.000 |
