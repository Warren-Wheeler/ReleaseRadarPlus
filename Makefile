.PHONY: fmt lint test run

run:
	python bot.py

test:
	python -m pip install -r requirements.txt pytest
	pytest -q

fmt:
	python -m pip install black==23.7.0 && black .

lint:
	python -m pip install flake8==6.1.0 && flake8 .
