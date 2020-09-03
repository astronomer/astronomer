# Public repository for charts.
.DEFAULT_GOAL := help

.PHONY: help
help: ## Print Makefile help
	@grep -Eh '^[0-9.a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

DOMAIN ?= helm.astronomer.io
URL    ?= https://${DOMAIN}
BUCKET ?= gs://${DOMAIN}

CHART_LIST := astronomer nginx grafana prometheus alertmanager fluentd kube-state postgresql
OUTPUT_DIR := repository
TEMP_DIR   := /tmp/${DOMAIN}

.PHONY: lint
lint: lint-prep lint-astro lint-charts ## Run all lint steps
#lint-prom (omitted)

venv:  ## Create the necessary python venv
	python3 -m venv venv
	. venv/bin/activate && pip install pyyaml

.PHONY: lint-prep
lint-prep:
	rm -rf ${TEMP_DIR}/astronomer || true
	mkdir -p ${TEMP_DIR}
	cp -R . ${TEMP_DIR}/astronomer

.PHONY: lint-astro
lint-astro: ## Lint the Astronomer helm chart
	helm lint ${TEMP_DIR}/astronomer

.PHONY: unittest-charts
unittest-charts: ## Run helm unittests on all charts
	helm plugin install https://github.com/astronomer/helm-unittest >/dev/null || true
	helm unittest -3 .

.PHONY: lint-charts
lint-charts: ## Lint all Helm charts
	# Check that nothing accidentally is using release name instead of namespace for metadata.namespace
	! helm template --namespace samplenamespace samplerelease . | grep 'namespace: samplerelease'
	# get a copy of the global values for helm lint'n the dependent charts
	python3 -c "import yaml; from pathlib import Path; globals = {'global': yaml.safe_load(Path('${TEMP_DIR}/astronomer/values.yaml').read_text())['global']}; Path('${TEMP_DIR}/globals.yaml').write_text(yaml.dump(globals))"
	find "${TEMP_DIR}/astronomer/charts" -mindepth 1 -maxdepth 1 -print0 | xargs -0 -n1 helm lint -f ${TEMP_DIR}/globals.yaml

.PHONY: lint-prom
lint-prom: ## Lint the prometheus helm charts
	# Lint the Prometheus alerts configuration
	helm template -s ${TEMP_DIR}/astronomer/charts/prometheus/templates/prometheus-alerts-configmap.yaml ${TEMP_DIR}/astronomer > ${TEMP_DIR}/prometheus_alerts.yaml
	# Parse the alerts.yaml data from the config map resource
	python3 -c "import yaml; from pathlib import Path; alerts = yaml.safe_load(Path('${TEMP_DIR}/prometheus_alerts.yaml').read_text())['data']['alerts']; Path('${TEMP_DIR}/prometheus_alerts.yaml').write_text(alerts)"
	promtool check rules ${TEMP_DIR}/prometheus_alerts.yaml

.PHONY: lint-clean
lint-clean:  ## Delete lint artifacts
	rm -rf ${TEMP_DIR} venv

.PHONY: local-test
local-test: ## Run a local chart test in kind
	bin/run-ci platform postgresql kubed keda

.PHONY: build
build: ## Build the helm chart for distribution
	helm repo add kedacore https://kedacore.github.io/charts
	rm -rf ${TEMP_DIR}/astronomer || true
	mkdir -p ${TEMP_DIR}
	cp -R . ${TEMP_DIR}/astronomer
	find "${TEMP_DIR}/astronomer/charts" -name requirements.yaml -type f -print | while read -r FILE ; do ( set -x ; cd `dirname $$FILE` && helm dep update ; ) ; done ;
	helm package ${TEMP_DIR}/astronomer

.PHONY: clean
clean: ## Clean all artifacts
	rm -rf venv ${TEMP_DIR}/astronomer

.PHONY: test
test: unittest-charts local-test ## Run unittests and local kind tests
