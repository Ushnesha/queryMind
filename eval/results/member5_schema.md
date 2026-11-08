# QueryMind Milestone 2 preliminary evaluation

Milestone 2 preliminary paired flat-versus-Neo4j schema comparison

These are recorded local measurements. N/A means no labelled cases or no instrumentation.

| Metric | flat | neo4j |
|---|---:|---:|
| Questions | 8 | 8 |
| Accuracy | 12.5% | 12.5% |
| Scored cases | 8.000 | 8.000 |
| Unscored cases | 0.000 | 0.000 |
| Reference errors | 0.000 | 0.000 |
| Easy accuracy | N/A | N/A |
| Hard accuracy | 12.5% | 12.5% |
| Completion | 12.5% | 12.5% |
| Execution success | 12.5% | 12.5% |
| Informed unanswerable refusal | N/A | N/A |
| Raw unanswerable refusal | N/A | N/A |
| Fabrication proxy | N/A | N/A |
| Ambiguity flagged | 0.0% | 0.0% |
| Over-refusal | 87.5% | 87.5% |
| LLM calls/question | 0.000 | 0.000 |
| Generations/question | 1.000 | 1.000 |
| p50 latency (ms) | 0.867 | 0.855 |
| p95 latency (ms) | 2.521 | 1.728 |

**flat:** Best means top three by total spending. Usually means arithmetic mean of order amounts for customers with orders.

**flat providers:** MockProvider

**flat placeholders/fallbacks:** result_verifier, semantic_verifier

**neo4j:** Best means top three by total spending. Usually means arithmetic mean of order amounts for customers with orders.

**neo4j providers:** MockProvider

**neo4j placeholders/fallbacks:** result_verifier, schema_retriever, semantic_verifier

Question IDs: H1, H2, H3, H4, H5, H6, A1, A2


## Schema retrieval comparison

| Metric | Flat | Neo4j |
|---|---:|---:|
| result_accuracy | 0.125 | 0.125 |
| correct_tables_rate | N/A | N/A |
| correct_join_path_rate | N/A | N/A |
| mean_schema_context_chars | 285.000 | 356.000 |
| mean_retrieval_latency_ms | 0.429 | 0.335 |
| fallback_runs | 0.000 | 8.000 |

## Interpretation

Mock generations do not call an LLM and are deterministic; repeated agreement does not establish a self-consistency benefit. Placeholder semantic/result checks and a Neo4j fallback must not be interpreted as validated components. A successful answer to a labelled unanswerable question is the fabrication proxy; generic unsupported-question refusals are not informed missing-field refusals. Accuracy uses exact column labels and unordered row multisets from the shared scorer. Ambiguous references document one interpretation. Latency is a single local observation per question, not a repeated model benchmark.
