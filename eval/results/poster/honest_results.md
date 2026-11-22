**Honest results (60-question set, run r1)**

*Where QueryMind beats b1*
- Ambiguity flagged: 7/12 vs 0/12

*Where it does not*
- Over-refusal: 8/44 vs 3/44
- Execution success: 36/60 vs 41/60
- Tie — Easy accuracy: 14/15 vs 14/15
- Tie — Hard accuracy: 12/20 vs 12/20
- Tie — Unanswerable: correct refusal: 16/16 vs 16/16
- Tie — False answers on unanswerable: 0/16 vs 0/16

*What it costs*
- 3.3× the LLM calls of b1
- 4.3× the tokens of b1
- p50 latency on answered questions 11.1 s vs 4.2 s

Overall (all questions, paired): QueryMind alone correct on 9, b1 alone on 3; exact McNemar p = 0.15. Not a significant difference at n = 60.
