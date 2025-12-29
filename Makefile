# UniFi Network Rules - Development Makefile
# Run 'make help' for available commands

.PHONY: help venv install lint lint-fix format fix test test-cov test-watch clean check all

# Detect venv - prefer existing venv/, then .venv/
VENV_DIR := $(shell if [ -d "venv" ]; then echo "venv"; elif [ -d ".venv" ]; then echo ".venv"; else echo "venv"; fi)
VENV_BIN := $(VENV_DIR)/bin
PYTHON := $(VENV_BIN)/python
PIP := $(VENV_BIN)/pip
RUFF := $(VENV_BIN)/ruff
PYTEST := $(VENV_BIN)/pytest

# Default target
help:
	@echo "UniFi Network Rules - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make venv        Create a Python virtual environment"
	@echo "  make install      Install dependencies"
	@echo ""
	@echo "Quality:"
	@echo "  make lint         Run Ruff linter"
	@echo "  make lint-fix     Run Ruff and auto-fix issues"
	@echo "  make format       Format code with Ruff"
	@echo "  make fix          Auto-fix + format (recommended)"
	@echo "  make check        Run all checks (lint + test)"
	@echo ""
	@echo "Testing:"
	@echo "  make test         Run tests"
	@echo "  make test-cov     Run tests with coverage report"
	@echo "  make test-watch   Run tests in watch mode"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean        Remove cache and build artifacts"

# Setup
venv:
	@if [ -d "venv" ] || [ -d ".venv" ]; then \
		echo "Virtual environment already exists at $(VENV_DIR)/"; \
	else \
		echo "Creating virtual environment..."; \
		python3 -m venv venv; \
		echo "Virtual environment created. Run 'make install' to install dependencies."; \
	fi
	@echo ""
	@echo "To activate: source $(VENV_DIR)/bin/activate"

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PIP) install -r requirements.txt

# Linting
lint:
	$(RUFF) check custom_components/ tests/

lint-fix:
	$(RUFF) check --fix custom_components/ tests/

format:
	$(RUFF) format custom_components/ tests/

fix: lint-fix format
	@echo ""
	@echo "Auto-fix and format complete!"

# Testing
test:
	$(PYTEST)

test-cov:
	$(PYTEST) --cov=custom_components/unifi_network_rules --cov-report=term-missing --cov-report=html
	@echo ""
	@echo "Coverage report generated: htmlcov/index.html"

test-watch:
	$(PYTEST) --watch

# Combined checks (mirrors CI)
check: lint test
	@echo ""
	@echo "All checks passed!"

# Full CI simulation
all: lint test-cov
	@echo ""
	@echo "Full CI simulation complete!"

# Cleanup
clean:
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf .mypy_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf coverage.xml
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
