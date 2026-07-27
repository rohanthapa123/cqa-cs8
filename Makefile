.PHONY: dev backend frontend install test

SHELL := /bin/bash
VENV := backend/.venv
export NVM_DIR := $(HOME)/.nvm

# Load nvm and select the Node version from .nvmrc (v20).
LOAD_NODE := . "$(NVM_DIR)/nvm.sh" && nvm use >/dev/null

# Run backend + frontend together; Ctrl+C stops both.
dev:
	@echo "Backend  -> http://localhost:8000"
	@echo "Frontend -> http://localhost:3000"
	@trap 'kill 0' INT TERM EXIT; \
	$(VENV)/bin/uvicorn backend.main:app --reload & \
	( $(LOAD_NODE) && cd frontend && npm run dev ) & \
	wait

backend:
	$(VENV)/bin/uvicorn backend.main:app --reload

frontend:
	$(LOAD_NODE) && cd frontend && npm run dev

install:
	$(VENV)/bin/pip install -r backend/requirements.txt
	$(LOAD_NODE) && cd frontend && npm install

test:
	$(VENV)/bin/python -m pytest backend/tests -q
