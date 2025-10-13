.DEFAULT_GOAL := help

.PHONY: help
help: ## Print Makefile help.
	@grep -Eh '^[a-z.A-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[1;36m%-41s\033[0m %s\n", $$1, $$2}'

# List of charts to build
CHARTS := astronomer nginx grafana prometheus alertmanager elasticsearch vector kube-state postgresql

TEMPDIR := /tmp/astro-temp
PATH := ${HOME}/.local/share/astronomer-software/bin:$(PATH)

.PHONY: venv
venv: .venv  ## Setup venv required for testing
.venv:
	[ -d .venv ] || { uv venv -p 3.13 --seed || python3 -m venv .venv -p python3 ; }
	.venv/bin/pip install -r tests/requirements.txt

.PHONY: test-functional-control
test-functional-control: export TEST_SCENARIO=control
test-functional-control: venv ## Run functional tests on the control installation scenario
	bin/reset-local-dev
	.venv/bin/python -m pytest -sv --junitxml=test-results/junit.xml tests/functional/$${TEST_SCENARIO}

.PHONY: test-functional-data
test-functional-data: export TEST_SCENARIO=data
test-functional-data: venv ## Run functional tests on the data installation scenario
	bin/reset-local-dev
	.venv/bin/python -m pytest -sv --junitxml=test-results/junit.xml tests/functional/$${TEST_SCENARIO}

.PHONY: test-functional-unified
test-functional-unified: export TEST_SCENARIO=unified
test-functional-unified: venv ## Run functional tests on the unified installation scenario
	bin/reset-local-dev
	.venv/bin/python -m pytest -sv --junitxml=test-results/junit.xml tests/functional/$${TEST_SCENARIO}

# unittest-charts is deprecated
.PHONY: unittest-charts
unittest-charts: test-unit
.PHONY: test-unit
test-unit: venv ## Run unit tests
	# Protip: you can modify pytest behavior like: make unittest-charts PYTEST_ADDOPTS='-v --maxfail=1 --pdb -k "prometheus and 1.20"'
	.venv/bin/python -m pytest -v --junitxml=test-results/junit.xml -n auto tests/chart_tests

.PHONY: validate-commander-airflow-version
validate-commander-airflow-version: ## Validate that airflowChartVersion is the same in astronomer configs and the commander docker image
	bin/validate_commander_airflow_version

.PHONY: test
test: validate-commander-airflow-version test-unit test-functional ## Run all tests
	@echo "All tests passed"

.PHONY: clean
clean: ## Clean build and test artifacts
	rm -rfv ${TEMPDIR}
	rm -rfv .unittest-requirements
	rm -rfv .pytest_cache
	rm -rfv .ruff_cache
	rm -rfv .venv
	rm -rfv test-results
	find . -name __pycache__ -exec rm -rfv {} \+
	rm -rfv ~/.local/share/astronomer-software
	kind delete cluster -n control
	kind delete cluster -n data
	kind delete cluster -n kind
	kind delete cluster -n unified

.PHONY: build
build: ## Build the Astronomer helm chart
	bin/build-helm-chart.sh

.PHONY: update-requirements
update-requirements: ## Update all requirements.txt files
	uv pip compile --quiet --upgrade tests/requirements.in --output-file tests/requirements.txt
	-pre-commit run requirements-txt-fixer --all-files --show-diff-on-failure

.PHONY: show-docker-images
show-docker-images: ## Show all docker images and versions used in the helm chart
	@bin/show-docker-images.py --with-houston

.PHONY: show-docker-images-with-private-registry
show-docker-images-with-private-registry: ## Show all docker images and versions used in the helm chart with a privateRegistry set
	@bin/show-docker-images.py --private-registry --with-houston

.PHONY: show-downloaded-tool-versions
show-test-helper-tool-versions: ## Show the versions of helper tools that were downloaded during testing
	-~/.local/share/astronomer-software/bin/helm version --short
	-~/.local/share/astronomer-software/tests/kind version
	-~/.local/share/astronomer-software/bin/kubectl version --client
	-~/.local/share/astronomer-software/bin/mkcert --version

.PHONY: show-test-helper-files
show-test-helper-files: ## Show all the test helper files downloaded and created during testing
	@find ~/.local/share/astronomer-software/ -type f | sort

.PHONY: cache-docker-images
cache-docker-images: ## Cache all docker images used in the base helm chart
	bin/show-docker-images.py --no-enable-all-features | cut -w -f2 | xargs -t -r -n1 docker pull
