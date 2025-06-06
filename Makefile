.DEFAULT_GOAL := help

.PHONY: help
help: ## Print Makefile help.
	@grep -Eh '^[a-z.A-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[1;36m%-41s\033[0m %s\n", $$1, $$2}'

# List of charts to build
CHARTS := astronomer nginx prometheus alertmanager elasticsearch kibana fluentd kube-state postgresql

TEMPDIR := /tmp/astro-temp

# functional-requirements is deprecated
.PHONY: functional-requirements
functional-requirements: .venv-functional
.PHONY: venv-functional
venv-functional: .venv-functional  ## Setup venv required for unit testing the Astronomer helm chart
.venv-functional:
	[ -d venv ] || { uv venv venv -p 3.11 --seed || virtualenv venv -p python3 ; }
	venv/bin/pip install -r requirements/functional-tests.txt
	touch $@

# unittest-requirements is deprecated
.PHONY: unittest-requirements
unittest-requirements: .venv-unit
.PHONY: venv-unit
venv-unit: .venv-unit  ## Setup venv required for unit testing the Astronomer helm chart
.venv-unit:
	[ -d venv ] || { uv venv venv -p 3.11 --seed || virtualenv venv -p python3 ; }
	venv/bin/pip install -r requirements/chart-tests.txt
	touch $@

.PHONY: test-functional
test-functional: venv-functional ## Run functional tests on the Astronomer helm chart
	venv/bin/python -m pytest -v --junitxml=test-results/junit.xml tests/functional_tests

.PHONY: test-functional-control
test-functional-control: venv-functional ## Run functional tests on the control installation scenario
	venv/bin/python -m pytest -sv --junitxml=test-results/junit.xml tests/multi_cluster/control

.PHONY: test-functional-data
test-functional-data: venv-functional ## Run functional tests on the data installation scenario
	venv/bin/python -m pytest -sv --junitxml=test-results/junit.xml tests/multi_cluster/data

.PHONY: test-functional-unified
test-functional-unified: venv-functional ## Run functional tests on the unified installation scenario
	venv/bin/python -m pytest -sv --junitxml=test-results/junit.xml tests/multi_cluster/unified

# unittest-charts is deprecated
.PHONY: unittest-charts
unittest-charts: test-unit
.PHONY: test-unit
test-unit: venv-unit ## Run unit tests
	# Protip: you can modify pytest behavior like: make unittest-charts PYTEST_ADDOPTS='-v --maxfail=1 --pdb -k "prometheus and 1.20"'
	venv/bin/python -m pytest -v --junitxml=test-results/junit.xml -n auto tests/chart_tests

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
	rm -rfv .venv*
	rm -rfv test-results
	rm -rfv venv
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
	for FILE in requirements/*.in ; do uv pip compile --quiet --upgrade $${FILE} --output-file $${FILE%.in}.txt ; done ;
	-pre-commit run requirements-txt-fixer --all-files --show-diff-on-failure

.PHONY: show-docker-images
show-docker-images: ## Show all docker images and versions used in the helm chart
	@bin/show-docker-images.py --with-houston

.PHONY: show-docker-images-with-private-registry
show-docker-images-with-private-registry: ## Show all docker images and versions used in the helm chart with a privateRegistry set
	@bin/show-docker-images.py --private-registry --with-houston

.PHONY: show-downloaded-tool-versions
show-downloaded-tool-versions: ## Show the versions of tools that were downloaded by multi-cluster test setup
	-~/.local/share/astronomer-software/bin/helm version --short
	-~/.local/share/astronomer-software/bin/kind version
	-~/.local/share/astronomer-software/bin/kubectl version --client
	-~/.local/share/astronomer-software/bin/mkcert --version
