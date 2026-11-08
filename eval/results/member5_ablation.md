# QueryMind Milestone 2 preliminary evaluation

Milestone 2 preliminary node-by-node ablation; one factor changed per variant

These are recorded local measurements. N/A means no labelled cases or no instrumentation.

| Metric | all_enabled | without_neo4j | without_semantic | without_result_verifier | without_optimizer | without_syntax |
|---|---:|---:|---:|---:|---:|---:|
| Questions | 10 | 10 | 10 | 10 | 10 | 10 |
| Accuracy | 20.0% | 20.0% | 20.0% | 20.0% | 20.0% | 20.0% |
| Scored cases | 10.000 | 10.000 | 10.000 | 10.000 | 10.000 | 10.000 |
| Unscored cases | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Reference errors | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Easy accuracy | 25.0% | 25.0% | 25.0% | 25.0% | 25.0% | 25.0% |
| Hard accuracy | 16.7% | 16.7% | 16.7% | 16.7% | 16.7% | 16.7% |
| Completion | 20.0% | 20.0% | 20.0% | 20.0% | 20.0% | 20.0% |
| Execution success | 20.0% | 20.0% | 20.0% | 20.0% | 20.0% | 20.0% |
| Informed unanswerable refusal | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Raw unanswerable refusal | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| Fabrication proxy | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Ambiguity flagged | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Over-refusal | 75.0% | 75.0% | 75.0% | 75.0% | 75.0% | 75.0% |
| LLM calls/question | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Generations/question | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| p50 latency (ms) | 0.879 | 0.998 | 0.889 | 0.990 | 0.791 | 0.860 |
| p95 latency (ms) | 2.510 | 1.899 | 2.017 | 2.102 | 1.500 | 1.450 |

**all_enabled:** Best means top three by total spending.

**all_enabled providers:** MockProvider

**all_enabled placeholders/fallbacks:** result_verifier, schema_retriever, semantic_verifier

**without_neo4j:** Best means top three by total spending.

**without_neo4j providers:** MockProvider

**without_neo4j placeholders/fallbacks:** result_verifier, semantic_verifier

**without_semantic:** Best means top three by total spending.

**without_semantic providers:** MockProvider

**without_semantic placeholders/fallbacks:** result_verifier, schema_retriever

**without_result_verifier:** Best means top three by total spending.

**without_result_verifier providers:** MockProvider

**without_result_verifier placeholders/fallbacks:** schema_retriever, semantic_verifier

**without_optimizer:** Best means top three by total spending.

**without_optimizer providers:** MockProvider

**without_optimizer placeholders/fallbacks:** result_verifier, schema_retriever, semantic_verifier

**without_syntax:** Best means top three by total spending.

**without_syntax providers:** MockProvider

**without_syntax placeholders/fallbacks:** result_verifier, schema_retriever, semantic_verifier

## Interpretation

Mock generations do not call an LLM and are deterministic; repeated agreement does not establish a self-consistency benefit. Placeholder semantic/result checks and a Neo4j fallback must not be interpreted as validated components. A successful answer to a labelled unanswerable question is the fabrication proxy; generic unsupported-question refusals are not informed missing-field refusals. Accuracy uses exact column labels and unordered row multisets from the shared scorer. Ambiguous references document one interpretation. Latency is a single local observation per question, not a repeated model benchmark.
