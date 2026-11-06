# Spider schema retrieval experiment

Backend: **Neo4j (live)**. Cases: 10. Generation: enabled.

| Metric | Flat schema | Neo4j (live) |
|---|---:|---:|
| Required table recall | 100.0% | 100.0% |
| Table precision | 45.8% | 85.8% |
| Exact table set | 0.0% | 60.0% |
| Required column recall | 100.0% | 100.0% |
| Column precision | 17.6% | 32.6% |
| Required FK-edge recall | 100.0% | 100.0% |
| FK-edge precision | 35.7% | 80.0% |
| Complete required join path | 100.0% | 100.0% |
| Mean context tokens/estimate | 269.80 | 135.00 |
| Mean retrieval latency (ms) | 1.57 | 35.61 |
| Median retrieval latency (ms) | 1.13 | 25.52 |
| SQL generation success | 70.0% | 80.0% |
| Syntax/safety success | 70.0% | 80.0% |
| Execution success | 70.0% | 80.0% |
| Result accuracy | 60.0% | 60.0% |
| Mean successful execution latency (ms) | 0.48 | 0.48 |

Token method: `lexical_regex_estimate_words_and_punctuation`.

## Per-case retrieval

| Case (zero-based source index) | Database | Required tables | Flat table recall | Graph table recall | Graph complete join path |
|---|---|---:|---:|---:|---:|
| spider_dev_0535 (535) | student_transcripts_tracking | 3 | 100% | 100% | yes |
| spider_dev_0515 (515) | student_transcripts_tracking | 2 | 100% | 100% | yes |
| spider_dev_0936 (936) | dog_kennels | 3 | 100% | 100% | yes |
| spider_dev_0930 (930) | dog_kennels | 2 | 100% | 100% | yes |
| spider_dev_0099 (99) | car_1 | 4 | 100% | 100% | yes |
| spider_dev_0089 (89) | car_1 | 2 | 100% | 100% | yes |
| spider_dev_0037 (37) | concert_singer | 3 | 100% | 100% | yes |
| spider_dev_0022 (22) | concert_singer | 2 | 100% | 100% | yes |
| spider_dev_0353 (353) | cre_Doc_Template_Mgt | 3 | 100% | 100% | yes |
| spider_dev_0307 (307) | cre_Doc_Template_Mgt | 2 | 100% | 100% | yes |

## Controls and limits

- Ten gold-selected cases are a small controlled sample, not the official Spider benchmark.
- Flat full-schema recall is expected to be 100%; precision/context size measure selectivity separately.
- Local graph diagnostics do not establish Neo4j service latency or live end-to-end gains.
- Retrieval-only reports have no SQL execution or result-accuracy measurement.
- Unordered result comparison does not verify requested row ordering or answer prose.
- Model generation can vary even at temperature zero; no causal claim from one run.

The JSON sibling contains source hashes, fixed controls, all retrieved contexts, qualified tables/columns/FK edges, timing samples, and generated SQL/results when enabled.
