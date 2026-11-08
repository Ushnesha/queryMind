PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
QUESTION ?= Who are the top 3 customers by total spending?
DEMO_DB ?= data/analytics.db
REPORT_DIR ?= eval/results/integrated

.PHONY: test seed demo baseline-demo ui eval ablation score verify-data schema-graph benchmark

test:
	$(PYTHON) -m pytest -q

seed:
	$(PYTHON) -m scripts.seed_db --db "$(DEMO_DB)"

demo: seed
	SQLITE_DB="$(DEMO_DB)" $(PYTHON) -m src.run --schema-mode flat --question "$(QUESTION)" --trace logs/demo.jsonl

baseline-demo: seed
	SQLITE_DB="$(DEMO_DB)" $(PYTHON) -m src.baseline --question "$(QUESTION)" --trace logs/baseline.jsonl

ui: seed
	SQLITE_DB="$(DEMO_DB)" $(PYTHON) -m streamlit run app.py

eval: seed
	$(PYTHON) -m scripts.run_eval --db-path "$(DEMO_DB)" --arm all --output "$(REPORT_DIR)/comparison.json" --markdown "$(REPORT_DIR)/comparison.md"

ablation: seed
	$(PYTHON) -m scripts.run_ablation --db-path "$(DEMO_DB)" --include-syntax --output "$(REPORT_DIR)/ablation.json" --markdown "$(REPORT_DIR)/ablation.md"

score: eval

verify-data:
	SQLITE_DB="$(DEMO_DB)" $(PYTHON) -m src.baseline --question "How many customers are there?"

schema-graph: seed
	$(PYTHON) -m scripts.build_schema_graph --db "$(DEMO_DB)"

benchmark: seed
	$(PYTHON) -m scripts.benchmark_optimizer --out "$(REPORT_DIR)"
