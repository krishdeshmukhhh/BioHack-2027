-include .env
export

PY := .venv/bin/python
PIP := .venv/bin/pip
HUB_PORT ?= 8000

.PHONY: setup broker hub sim history test lint fw-build fw-upload fw-monitor lanes lanes-status

setup:
	python3 -m venv .venv
	$(PIP) install -r requirements.txt

broker:
	mkdir -p .mosquitto
	mosquitto -c scripts/mosquitto.conf

hub:
	$(PY) -m uvicorn hub.app.main:app --host 0.0.0.0 --port $(HUB_PORT) --reload

sim:
	$(PY) -m sim.pump_sim

history:
	$(PY) -m sim.generate_history

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .

fw-build:
	cd firmware && pio run

fw-upload:
	cd firmware && pio run -t upload

fw-monitor:
	cd firmware && pio device monitor

lanes:
	scripts/worktrees.sh up

lanes-status:
	scripts/worktrees.sh status
