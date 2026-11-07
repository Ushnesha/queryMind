# Spider schema retrieval experiment

Backend: **Local graph (offline diagnostic)**. Cases: 10. Generation: disabled; execution/result accuracy are TBD.

| Metric | Flat schema | Local graph (offline diagnostic) |
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
| Mean retrieval latency (ms) | 0.76 | 0.87 |
| Median retrieval latency (ms) | 0.47 | 0.54 |
| SQL generation success | TBD (generation disabled) | TBD (generation disabled) |
| Syntax/safety success | TBD (generation disabled) | TBD (generation disabled) |
| Execution success | TBD (generation disabled) | TBD (generation disabled) |
| Result accuracy | TBD (generation disabled) | TBD (generation disabled) |
| Mean successful execution latency (ms) | TBD (generation disabled) | TBD (generation disabled) |

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
