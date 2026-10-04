-include .env
export

PY := .venv/bin/python
PIP := .venv/bin/pip
HUB_PORT ?= 8000

.PHONY: fw-test setup broker hub sim history reset-demo docker-up docker-sim docker-logs docker-down docker-reset test lint fw-build fw-upload fw-monitor lanes lanes-status

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

reset-demo:
	scripts/reset_demo.sh

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

# Docker hub stack (replaces the Raspberry Pi). Build once while online.
docker-up:
	docker compose up -d --build broker hub dashboard

docker-sim:
	docker compose --profile sim run --rm sim

docker-logs:
	docker compose logs -f broker hub

docker-down:
	docker compose down

# On Windows, make from PowerShell has no sh, and the bash on PATH there is WSL's: use Git Bash.
ifeq ($(OS),Windows_NT)
RESET_BASH := "$(ProgramW6432)/Git/bin/bash.exe"
else
RESET_BASH := bash
endif

docker-reset:
	$(RESET_BASH) scripts/reset_demo_docker.sh

# Firmware native tests (incl. the 55 shared prescription cases) and the digital demo
# tests. Needs PlatformIO; not part of make test because not every laptop has it.
fw-test:
	cd firmware && pio test -e native && pio run -e native
	$(PY) -m pytest -q firmware/test
