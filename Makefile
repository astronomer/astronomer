.DEFAULT_GOAL := help

.PHONY: help
help: ## Print Makefile help.
	@grep -Eh '^[a-z.A-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-41s\033[0m %s\n", $$1, $$2}'

# List of charts to build
CHARTS := astronomer nginx grafana prometheus alertmanager elasticsearch kibana fluentd kube-state postgresql

TEMPDIR := /tmp/astro-temp

.PHONY: lint
lint: lint-prep lint-astro lint-charts ## Run all lint steps on the Astronomer helm chart and subcharts

.PHONY: lint-prep
lint-prep: ## Prepare a clean env for linting
	rm -rf ${TEMPDIR}/astronomer || true
	mkdir -p ${TEMPDIR}
	cp -R . ${TEMPDIR}/astronomer

.PHONY: lint-astro
lint-astro: lint-prep ## Lint the Astronomer helm chart
	helm lint ${TEMPDIR}/astronomer

unittest-requirements: .unittest-requirements ## Setup venv required for unit testing the Astronomer helm chart
.unittest-requirements:
	[ -d venv ] || virtualenv venv -p python3
	venv/bin/pip install -r requirements/chart-tests.txt
	touch .unittest-requirements

.PHONY: unittest-charts
unittest-charts: .unittest-requirements ## Unittest the Astronomer helm chart
	venv/bin/python -m pytest -n auto tests

.PHONY: lint-charts
lint-charts: lint-prep ## Lint Astronomer sub-charts
	# Check that nothing accidentally is using release name instead of namespace for metadata.namespace
	! helm template --namespace samplenamespace samplerelease . | grep 'namespace: samplerelease'
	# get a copy of the global values for helm lint'n the dependent charts
	python3 -c "import yaml; from pathlib import Path; globals = {'global': yaml.safe_load(Path('${TEMPDIR}/astronomer/values.yaml').read_text())['global']}; Path('${TEMPDIR}/globals.yaml').write_text(yaml.dump(globals))"
	find "${TEMPDIR}/astronomer/charts" -mindepth 1 -maxdepth 1 -print0 | xargs -0 -n1 helm lint -f ${TEMPDIR}/globals.yaml

.PHONY: lint-prom
lint-prom: ## Lint the Prometheus alerts configuration
	helm template -s ${TEMPDIR}/astronomer/charts/prometheus/templates/prometheus-alerts-configmap.yaml ${TEMPDIR}/astronomer > ${TEMPDIR}/prometheus_alerts.yaml
	# Parse the alerts.yaml data from the config map resource
	python3 -c "import yaml; from pathlib import Path; alerts = yaml.safe_load(Path('${TEMPDIR}/prometheus_alerts.yaml').read_text())['data']['alerts']; Path('${TEMPDIR}/prometheus_alerts.yaml').write_text(alerts)"
	promtool check rules ${TEMPDIR}/prometheus_alerts.yaml

.PHONY: clean
clean: ## Clean build and test artifacts
	rm -rf ${TEMPDIR}
	rm -f .unittest-requirements
	rm -rf venv

.PHONY: build
build: ## Build the Astronomer helm chart
	bin/build-helm-chart.sh

.PHONY: update-requirements
update-requirements: ## Update all requirements.txt files
	for FILE in requirements/*.in ; do pip-compile --quiet --generate-hashes --allow-unsafe --upgrade $${FILE} ; done ;
	-pre-commit run requirements-txt-fixer --all-files --show-diff-on-failure

.PHONY: show-docker-images
show-docker-images: ## Show all docker images and versions used in the helm chart
	@helm template . \
		--set global.baseDomain=foo.com \
		--set global.blackboxExporterEnabled=True \
		--set global.postgresqlEnabled=True \
		--set global.postgresqlEnabled=True \
		--set global.prometheusPostgresExporterEnabled=True \
		--set global.pspEnabled=True \
		--set global.veleroEnabled=True \
		2>/dev/null \
		| awk '/image: / {match($$2, /(([^"]*):[^"]*)/, a) ; printf "https://%s %s\n", a[2], a[1] ;}' | sort -u | column -t

.PHONY: show-docker-images
show-docker-images-with-private-registry: ## Show all docker images and versions used in the helm chart with a privateRegistry set
	@helm template . \
		--set global.privateRegistry.enabled=True \
		--set global.privateRegistry.repository=example.com/the-private-registry \
		--set global.baseDomain=foo.com \
		--set global.blackboxExporterEnabled=True \
		--set global.postgresqlEnabled=True \
		--set global.prometheusPostgresExporterEnabled=True \
		--set global.pspEnabled=True \
		--set global.veleroEnabled=True \
		2>/dev/null \
		| awk '/image: / {match($$2, /(([^"]*):[^"]*)/, a) ; printf "https://%s %s\n", a[2], a[1] ;}' | sort -u | column -t
