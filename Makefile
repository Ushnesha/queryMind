PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
QUESTION ?= Who are the top 3 customers by total spending?

.PHONY: test seed demo baseline-demo ui eval ablation score verify-data schema-graph benchmark

test:
	$(PYTHON) -m pytest -q

seed:
	$(PYTHON) -m scripts.seed_db

demo: seed
	$(PYTHON) -m src.run --schema-mode flat --question "$(QUESTION)" --trace logs/demo.jsonl

baseline-demo: seed
	$(PYTHON) -m src.baseline --question "$(QUESTION)" --trace logs/baseline.jsonl

ui:
	$(PYTHON) -m streamlit run app.py

eval: seed
	$(PYTHON) -m scripts.run_eval --output eval/results/starter.json

ablation: seed
	$(PYTHON) -m scripts.run_ablation --output eval/results/ablation.json

score: eval

verify-data:
	$(PYTHON) -m src.baseline --question "How many customers are there?"

schema-graph: seed
	$(PYTHON) -m scripts.build_schema_graph

benchmark: seed
	$(PYTHON) -m scripts.benchmark_optimizer
