PYTHON ?= python3
PIP ?= pip
# Prefer bun for setup if it exists
NPM ?= $(shell if [ -f /root/.bun/bin/bun ]; then echo /root/.bun/bin/bun; else echo npm; fi)

.PHONY: setup system-setup python-setup node-setup test-python test-js test-all test

# Full setup for a new container environment
setup: system-setup python-setup node-setup

# Install OS-level dependencies (Node.js 20, Bun, etc.)
system-setup:
	@echo "Installing OS-level dependencies..."
	apt-get update && apt-get install -y curl ca-certificates unzip
	curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
	apt-get install -y nodejs
	@echo "Installing Bun..."
	curl -fsSL https://bun.sh/install | bash

# Python-specific setup
python-setup:
	@echo "Installing Python dependencies..."
	$(PIP) install -r requirements.txt
	$(PIP) install -e .
	$(PYTHON) -m playwright install chromium

# Node.js-specific setup
node-setup:
	@echo "Installing Node.js dependencies..."
	[ -f .env ] || cp .env.example .env
	# Add bun to PATH if it was just installed (standard location is /root/.bun/bin)
	export PATH="/root/.bun/bin:$$PATH" && cd .opencode && $(NPM) install

test-python:
	pytest market/ tests/

test-logic:
	pytest market/ tests/ --ignore=market/dashboard_startup_test.py --ignore=market/integration_dashboard_test.py --ignore=market/elo/regression_test.py

test-elo:
	pytest market/elo/regression_test.py

test-elo-fib:
	python3 -m market.elo.cli run --prompt "compute fibonacci #s" --agents 3 --max-duration 20

test-ui:
	pytest market/dashboard_startup_test.py market/integration_dashboard_test.py
	cd .opencode && npx vitest run

test-js:
	cd .opencode && npx vitest run

test-all: test-python test-js test-elo

test: test-logic test-elo

test-fib:
	npx opencode run "run a tournament with 3 agents for 1 round to compute fibonacci #s"
