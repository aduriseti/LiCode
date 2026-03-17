.PHONY: setup test-python test-js test-all test

setup:
	pip install -r requirements.txt
	pip install -e .
	python3 -m playwright install chromium
	cd .opencode && npm install
	[ -f .env ] || cp .env.example .env

test-python:
	pytest market/ tests/

test-js:
	cd .opencode && npx vitest run

test-all: test-python test-js

test: test-all

test-fib:
	npx opencode run "run a tournament with 3 agents for 1 round to compute fibonacci #s"
