.DEFAULT_GOAL := help

.PHONY: help
help: ## Print Makefile help.
	@grep -Eh '^[a-z.A-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[1;36m%-41s\033[0m %s\n", $$1, $$2}'

# List of charts to build
CHARTS := astronomer nginx grafana prometheus alertmanager elasticsearch kibana fluentd kube-state postgresql

TEMPDIR := /tmp/astro-temp

unittest-requirements: .unittest-requirements ## Setup venv required for unit testing the Astronomer helm chart
.unittest-requirements:
	[ -d venv ] || virtualenv venv -p python3
	venv/bin/pip install -r requirements/chart-tests.txt
	touch .unittest-requirements

.PHONY: unittest-charts
unittest-charts: .unittest-requirements ## Unittest the Astronomer helm chart
	# Protip: you can modify pytest behavior like: make unittest-charts PYTEST_ADDOPTS='-v --maxfail=1 --pdb -k "prometheus and 1.20"'
	venv/bin/python -m pytest -v --junitxml=test-results/junit.xml -n auto tests/chart_tests

.PHONY: validate-commander-airflow-version
validate-commander-airflow-version: ## Validate that airflowChartVersion is the same in astronomer configs and the commander docker image
	bin/validate_commander_airflow_version

.PHONY: test
test: validate-commander-airflow-version unittest-charts

.PHONY: clean
clean: ## Clean build and test artifacts
	rm -rf ${TEMPDIR}
	rm -f .unittest-requirements
	rm -rf venv
	rm -rf .pytest_cache
	rm -rf test-results
	find . -name __pycache__ -exec rm -rf {} \+

.PHONY: build
build: ## Build the Astronomer helm chart
	bin/build-helm-chart.sh

.PHONY: update-requirements
update-requirements: ## Update all requirements.txt files
	for FILE in requirements/*.in ; do pip-compile --quiet --generate-hashes --allow-unsafe --upgrade $${FILE} ; done ;
	-pre-commit run requirements-txt-fixer --all-files --show-diff-on-failure

.PHONY: show-docker-images
show-docker-images: ## Show all docker images and versions used in the helm chart
	@bin/show-docker-images.py --with-houston

.PHONY: show-docker-images-with-private-registry
show-docker-images-with-private-registry: ## Show all docker images and versions used in the helm chart with a privateRegistry set
	@bin/show-docker-images.py --private-registry --with-houston
