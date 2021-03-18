# List of charts to build
CHARTS := astronomer nginx grafana prometheus alertmanager elasticsearch kibana fluentd kube-state postgresql

TEMPDIR := /tmp/astro-temp

.PHONY: lint
lint: lint-prep lint-astro lint-charts

.PHONY: lint-venv
lint-venv:
	python3 -m venv venv
	. venv/bin/activate && pip install pyyaml

.PHONY: lint-prep
lint-prep:
	rm -rf ${TEMPDIR}/astronomer || true
	mkdir -p ${TEMPDIR}
	cp -R . ${TEMPDIR}/astronomer

.PHONY: lint-astro
lint-astro:
	helm lint ${TEMPDIR}/astronomer

.PHONY: unittest-charts
unittest-charts:
	helm plugin install https://github.com/quintush/helm-unittest >/dev/null || true
	helm unittest -3 .

.PHONY: lint-charts
lint-charts:
	# Check that nothing accidentally is using release name instead of namespace for metadata.namespace
	! helm template --namespace samplenamespace samplerelease . | grep 'namespace: samplerelease'
	# get a copy of the global values for helm lint'n the dependent charts
	python3 -c "import yaml; from pathlib import Path; globals = {'global': yaml.safe_load(Path('${TEMPDIR}/astronomer/values.yaml').read_text())['global']}; Path('${TEMPDIR}/globals.yaml').write_text(yaml.dump(globals))"
	find "${TEMPDIR}/astronomer/charts" -mindepth 1 -maxdepth 1 -print0 | xargs -0 -n1 helm lint -f ${TEMPDIR}/globals.yaml

.PHONY: lint-prom
lint-prom:
	# Lint the Prometheus alerts configuration
	helm template -s ${TEMPDIR}/astronomer/charts/prometheus/templates/prometheus-alerts-configmap.yaml ${TEMPDIR}/astronomer > ${TEMPDIR}/prometheus_alerts.yaml
	# Parse the alerts.yaml data from the config map resource
	python3 -c "import yaml; from pathlib import Path; alerts = yaml.safe_load(Path('${TEMPDIR}/prometheus_alerts.yaml').read_text())['data']['alerts']; Path('${TEMPDIR}/prometheus_alerts.yaml').write_text(alerts)"
	promtool check rules ${TEMPDIR}/prometheus_alerts.yaml

.PHONY: lint-clean
lint-clean:
	rm -rf ${TEMPDIR}

.PHONY: build
build:
	helm repo add kedacore https://kedacore.github.io/charts
	rm -rf ${TEMPDIR}/astronomer || true
	mkdir -p ${TEMPDIR}
	cp -R . ${TEMPDIR}/astronomer
	find "${TEMPDIR}/astronomer/charts" -name requirements.yaml -type f -print | while read -r FILE ; do ( set -x ; cd `dirname $$FILE` && helm dep update ; ) ; done ;
	helm package ${TEMPDIR}/astronomer
