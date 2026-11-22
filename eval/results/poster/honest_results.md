**Honest results (50-question set, run r1)**

*Where QueryMind beats b1*
- Hard accuracy: 10/17 vs 9/17
- Ambiguity flagged: 5/9 vs 0/9

*Where it does not*
- Over-refusal: 6/36 vs 1/36
- Execution success: 30/50 vs 35/50
- Tie — Easy accuracy: 12/13 vs 12/13
- Tie — Unanswerable: correct refusal: 14/14 vs 14/14
- Tie — False answers on unanswerable: 0/14 vs 0/14

*What it costs*
- 3.2× the LLM calls of b1
- 4.0× the tokens of b1
- p50 latency on answered questions 11.9 s vs 4.2 s

Overall (all questions, paired): QueryMind alone correct on 7, b1 alone on 2; exact McNemar p = 0.18. Not a significant difference at n = 50.
