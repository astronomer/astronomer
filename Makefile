# Public repository for charts.
DOMAIN ?= helm.astronomer.io
URL ?= https://${DOMAIN}
BUCKET ?= gs://${DOMAIN}

# Version
# ASTRONOMER_MAJOR_VERSION ?= 0
# ASTRONOMER_MINOR_VERSION ?= 5
# ASTRONOMER_PATCH_VERSION ?= 1
# ASTRONOMER_VERSION ?= ${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}

# List of charts to build
CHARTS := airflow astronomer nginx grafana prometheus alertmanager elasticsearch kibana fluentd kube-state

# Output directory
OUTPUT := repository

.PHONY: build
build: update-version
	mkdir -p ${OUTPUT}
	for chart in ${CHARTS} ; do \
		helm package --version ${ASTRONOMER_VERSION} -d ${OUTPUT} charts/$${chart} || exit 1; \
	done; \
	$(MAKE) build-index

.PHONY: build-index
build-index:
	helm repo index ${OUTPUT} --url ${URL} # --merge ${OUTPUT}/index.yaml

.PHONY: push
push: build
	@read -p "Are you sure you want to push a production release? Ctrl+c to abort." ans;
	$(MAKE) push-repo

.PHONY: push-repo
push-repo:
	for chart in ${CHARTS} ; do \
		gsutil cp -a public-read ${OUTPUT}/$${chart}-${ASTRONOMER_VERSION}.tgz ${BUCKET} || exit 1; \
	done; \
	$(MAKE) push-index

.PHONY: push-index
push-index: build-index
	gsutil cp -a public-read ${OUTPUT}/index.yaml ${BUCKET}

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
