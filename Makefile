PYTHON ?= python3
SYSTEM_VENV := .venv-system
SCRAPER_VENV := .venv-scraper

.PHONY: system-venv scraper-venv dev-venvs test-system test-scraper preflight-system

system-venv:
	$(PYTHON) -m venv $(SYSTEM_VENV)
	$(SYSTEM_VENV)/bin/pip install --upgrade pip
	$(SYSTEM_VENV)/bin/pip install -e ./system[dev]

scraper-venv:
	$(PYTHON) -m venv $(SCRAPER_VENV)
	$(SCRAPER_VENV)/bin/pip install --upgrade pip
	$(SCRAPER_VENV)/bin/pip install -e ./scraper[dev]

dev-venvs: system-venv scraper-venv

test-system:
	$(SYSTEM_VENV)/bin/pytest -q system/tests

test-scraper:
	$(SCRAPER_VENV)/bin/pytest -q scraper/tests

preflight-system:
	cd system && ../$(SYSTEM_VENV)/bin/python -m app.workers.preflight
