.PHONY: setup test

setup:
	pip install -r requirements.txt
	python3 -m playwright install chromium

test:
	export PYTHONPATH=$${PYTHONPATH}:$$(pwd) && export PATH=$${PATH}:$$(pwd)/.opencode/node_modules/.bin && pytest market/ tests/
