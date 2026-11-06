# QueryMind Milestone 2 preliminary evaluation

Preliminary paired comparison; b2-small k=3; deterministic mock unless a provider is configured.

These are recorded local measurements. N/A means no labelled cases or no instrumentation.

## Paired arm comparison

All arms use the same question IDs. b2 is reduced preliminary self-consistency, not the final k=5 configuration.

| Metric | b1 | b2-small | querymind |
|---|---:|---:|---:|
| Questions | 7 | 7 | 7 |
| Accuracy | 28.6% | 28.6% | 28.6% |
| Scored cases | 7.000 | 7.000 | 7.000 |
| Unscored cases | 0.000 | 0.000 | 0.000 |
| Reference errors | 0.000 | 0.000 | 0.000 |
| Easy accuracy | 50.0% | 50.0% | 50.0% |
| Hard accuracy | 20.0% | 20.0% | 20.0% |
| Completion | 28.6% | 28.6% | 28.6% |
| Execution success | 28.6% | 28.6% | 28.6% |
| Informed unanswerable refusal | 0.0% | 0.0% | 0.0% |
| Raw unanswerable refusal | 100.0% | 100.0% | 100.0% |
| Fabrication proxy | 0.0% | 0.0% | 0.0% |
| Ambiguity flagged | 0.0% | 0.0% | 0.0% |
| Over-refusal | 66.7% | 66.7% | 66.7% |
| LLM calls/question | 0.000 | 0.000 | 0.000 |
| Generations/question | 1.000 | 3.000 | 1.000 |
| p50 latency (ms) | 0.846 | 0.837 | 0.880 |
| p95 latency (ms) | 2.339 | 3.507 | 2.196 |

**b1:** Best means top three by total spending.

**b1 providers:** MockProvider

**b2-small:** Best means top three by total spending.

**b2-small providers:** MockProvider

**querymind:** Best means top three by total spending.

**querymind providers:** MockProvider

**querymind placeholders/fallbacks:** result_verifier, semantic_verifier

Question IDs: E1, E3, H1, H2, H3, U1, A1


## Full preliminary fixture (b2 excluded)

- b1: 2/17 correct; accuracy 11.8%.
- querymind: 2/17 correct; accuracy 11.8%.

## Interpretation

Mock generations do not call an LLM and are deterministic; repeated agreement does not establish a self-consistency benefit. Placeholder semantic/result checks and a Neo4j fallback must not be interpreted as validated components. A successful answer to a labelled unanswerable question is the fabrication proxy; generic unsupported-question refusals are not informed missing-field refusals. Accuracy uses exact column labels and unordered row multisets from the shared scorer. Ambiguous references document one interpretation. Latency is a single local observation per question, not a repeated model benchmark.
