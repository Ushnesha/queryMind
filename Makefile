PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
QUESTION ?= Who are the top 3 customers by total spending?
DEMO_DB ?= data/analytics.db
REPORT_DIR ?= eval/results/integrated

.PHONY: test seed demo baseline-demo ui eval ablation score verify-data schema-graph benchmark \
	stakeholder-baseline spider-pilot report-eval report-score

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

# --- Milestone report evaluation: stakeholder b0/b1 vs QueryMind, live model ---
STAKEHOLDER_REPO ?= https://github.com/Vinay-K-Veeramallu/agentic-sql-analyst.git
STAKEHOLDER_COMMIT ?= c0b0cda
STAKEHOLDER_DIR := external/agentic-sql-analyst
STAKEHOLDER_DB := data/stakeholder_analytics.db

stakeholder-baseline:
	test -d $(STAKEHOLDER_DIR) || git clone $(STAKEHOLDER_REPO) $(STAKEHOLDER_DIR)
	git -C $(STAKEHOLDER_DIR) checkout -q $(STAKEHOLDER_COMMIT)
	test -x $(STAKEHOLDER_DIR)/venv/bin/python || uv venv -q --python 3.11 $(STAKEHOLDER_DIR)/venv
	uv pip install -q --python $(STAKEHOLDER_DIR)/venv/bin/python -r $(STAKEHOLDER_DIR)/requirements-dev.txt
	$(STAKEHOLDER_DIR)/venv/bin/python $(STAKEHOLDER_DIR)/scripts/seed_db.py --db $(STAKEHOLDER_DB)
	$(PYTHON) -m scripts.build_schema_graph --db $(STAKEHOLDER_DB) --upload

spider-pilot:
	$(PYTHON) -m scripts.build_spider_pilot --size 50 --seed 598

report-eval:
	$(PYTHON) -m scripts.run_report_eval --dataset all

report-score:
	$(STAKEHOLDER_DIR)/venv/bin/python scripts/score_report_eval.py
