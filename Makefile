PY ?= python
export PYTHONPATH := pipeline

.PHONY: install pipeline rebuild test serve docker clean

install:        ## Install dependencies
	$(PY) -m pip install -r requirements-dev.txt

pipeline:       ## Download sources (~1.2 GB), build lake + warehouse, train models, export site data
	$(PY) -m pulse.run

rebuild:        ## Re-run SQL + models from the existing Parquet lake (no downloads)
	$(PY) -m pulse.run --skip-ingest

test:           ## Unit + integration tests on a synthetic mini-system
	$(PY) -m pytest -q

serve:          ## Preview the website at http://localhost:8000
	$(PY) -m http.server 8000 --directory docs

docker:         ## Run the whole pipeline in a container
	docker build -t ecobici-pulse .
	docker run --rm -v "$$PWD/data:/app/data" -v "$$PWD/docs/data:/app/docs/data" ecobici-pulse

clean:
	rm -rf data/lake data/warehouse.duckdb
