# Public repository for charts.
DOMAIN ?= helm.astronomer.io
URL ?= https://${DOMAIN}
BUCKET ?= gs://${DOMAIN}

# List of charts to build
CHARTS := astronomer nginx grafana prometheus alertmanager elasticsearch kibana fluentd kube-state postgresql

# Output directory
OUTPUT := repository

# Temp directory
TEMP := /tmp/${DOMAIN}


.PHONY: lint
lint: lint-prep lint-astro lint-charts 
#lint-prom (omitted)

.PHONY: lint-venv
.ONESHELL:
lint-venv:
	set -eu
	python3 -m venv venv
	. venv/bin/activate
	pip install pyyaml

.PHONY: lint-prep
.ONESHELL:
lint-prep:
	set -eu
	rm -rf ${TEMP}/astronomer || true
	mkdir -p ${TEMP}
	cp -R ../astronomer ${TEMP}/astronomer || cp -R ../project ${TEMP}/astronomer

.PHONY: lint-astro
.ONESHELL:
lint-astro:
	set -eu
	helm lint ${TEMP}/astronomer

.PHONY: lint-charts
.ONESHELL:
lint-charts:
	set -eu
	# Check that nothing accidentally is using release name instead of namespace for metadata.namespace
	! helm template --namespace samplenamespace samplerelease . | grep 'namespace: samplerelease'
	# get a copy of the global values for helm lint'n the dependent charts
	python3 -c "import yaml; from pathlib import Path; globals = {'global': yaml.safe_load(Path('${TEMP}/astronomer/values.yaml').read_text())['global']}; Path('${TEMP}/globals.yaml').write_text(yaml.dump(globals))"
	for chart in $$(ls ${TEMP}/astronomer/charts); do
	helm lint -f ${TEMP}/globals.yaml ${TEMP}/astronomer/charts/$$chart
	done

.PHONY: lint-prom
.ONESHELL:
lint-prom:
	set -eu
	# Lint the Prometheus alerts configuration
	helm template -s ${TEMP}/astronomer/charts/prometheus/templates/prometheus-alerts-configmap.yaml ${TEMP}/astronomer > ${TEMP}/prometheus_alerts.yaml
	# Parse the alerts.yaml data from the config map resource
	python3 -c "import yaml; from pathlib import Path; alerts = yaml.safe_load(Path('${TEMP}/prometheus_alerts.yaml').read_text())['data']['alerts']; Path('${TEMP}/prometheus_alerts.yaml').write_text(alerts)"
	promtool check rules ${TEMP}/prometheus_alerts.yaml

.PHONY: lint-clean
.ONESHELL:
lint-clean:
	rm -rf ${TEMP}


.PHONY: build
.ONESHELL:
build:
	set -xe
	helm repo add kedacore https://kedacore.github.io/charts
	rm -rf ${TEMP}/astronomer || true
	mkdir -p ${TEMP}
	cp -R ../astronomer ${TEMP}/astronomer || cp -R ../project ${TEMP}/astronomer
	# Install external charts
	for chart in $$(ls ${TEMP}/astronomer/charts); do
	if test -f ${TEMP}/astronomer/charts/$$chart/requirements.yaml; then
	helm dep update ${TEMP}/astronomer/charts/$$chart
	fi
	done
	helm package ${TEMP}/astronomer

.PHONY: build-index
build-index:
	wget ${DOMAIN}/index.yaml -O ${TEMP}
	helm repo index ${OUTPUT} --url ${URL} --merge ${TEMP}

.PHONY: push
push: build
	@read -p "Are you sure you want to push a production release? Ctrl+c to abort." ans;
	$(MAKE) push-repo

.PHONY: push-repo
push-repo:
	for chart in ${CHARTS} ; do \
		gsutil cp ${OUTPUT}/$${chart}-${ASTRONOMER_VERSION}.tgz ${BUCKET} || exit 1; \
	done; \
	$(MAKE) push-index

.PHONY: push-index
push-index: build-index
	gsutil -h "Cache-Control: public, max-age=300" cp ${OUTPUT}/index.yaml ${BUCKET}

.PHONY: clean
clean:
	for chart in ${CHARTS} ; do \
		rm ${OUTPUT}/$${chart}-${ASTRONOMER_VERSION}.tgz || exit 1; \
	done; \

.PHONY: update-image-tags
update-image-tags: check-env
	find charts -name 'values.yaml' -exec sed -i -E 's/tag: (0|[1-9][[:digit:]]*)\.(0|[1-9][[:digit:]]*)\.(0|[1-9][[:digit:]]*)(-(0|[1-9][[:digit:]]*|[[:digit:]]*[a-zA-Z-][0-9a-zA-Z-]*)(\.(0|[1-9][[:digit:]]*|[[:digit:]]*[a-zA-Z-][0-9a-zA-Z-]*))*)?(\+[0-9a-zA-Z-]+(\.[0-9a-zA-Z-]+)*)?/tag: ${ASTRONOMER_VERSION}/g' {} \;

.PHONY: update-chart-versions
update-chart-versions: check-env
	find . -name Chart.yaml -exec sed -i -E 's/(0|[1-9][[:digit:]]*)\.(0|[1-9][[:digit:]]*)\.(0|[1-9][[:digit:]]*)(-(0|[1-9][[:digit:]]*|[[:digit:]]*[a-zA-Z-][0-9a-zA-Z-]*)(\.(0|[1-9][[:digit:]]*|[[:digit:]]*[a-zA-Z-][0-9a-zA-Z-]*))*)?(\+[0-9a-zA-Z-]+(\.[0-9a-zA-Z-]+)*)?/${ASTRONOMER_VERSION}/g' {} \;

.PHONY: update-version
update-version: check-env update-image-tags update-chart-versions

.PHONY: check-env
check-env:
ifndef ASTRONOMER_VERSION
	$(error ASTRONOMER_VERSION is not set)
endif
