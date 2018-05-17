# Public repository for charts.
DOMAIN ?= helm.astronomer.io
URL ?= https://${DOMAIN}
BUCKET ?= gs://${DOMAIN}

# Version
ASTRONOMER_MAJOR_VERSION ?= 0
ASTRONOMER_MINOR_VERSION ?= 2
ASTRONOMER_PATCH_VERSION ?= 1
ASTRONOMER_VERSION ?= ${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}

# List of charts to build
CHARTS := astronomer airflow

# Output directory
OUTPUT := repository

.PHONY: build
build:
	mkdir -p ${OUTPUT}
	for chart in ${CHARTS} ; do \
		helm package --version ${ASTRONOMER_VERSION} -d ${OUTPUT} charts/$${chart} || exit 1; \
	done; \
	helm repo index ${OUTPUT} --url ${URL}

.PHONY: push-public
push-public: build
	for chart in ${CHARTS} ; do \
		gsutil cp -a public-read ${OUTPUT}/$${chart}-${ASTRONOMER_VERSION}.tgz ${BUCKET} || exit 1; \
	done; \
	gsutil cp -a public-read ${OUTPUT}/configs/airflow-${ASTRONOMER_VERSION}.yaml ${BUCKET}/configs
	gsutil cp -a public-read ${OUTPUT}/index.yaml ${BUCKET}
