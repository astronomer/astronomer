# Public repository for charts.
URL ?= http://helm.astronomer.io

# Version
ASTRONOMER_MAJOR_VERSION ?= 0
ASTRONOMER_MINOR_VERSION ?= 0
ASTRONOMER_PATCH_VERSION ?= 1
ASTRONOMER_VERSION ?= ${ASTRONOMER_MAJOR_VERSION}.${ASTRONOMER_MINOR_VERSION}.${ASTRONOMER_PATCH_VERSION}

# List of charts to build
CHARTS := astronomer airflow clickstream

# Output directory
OUTPUT := docs

build:
	for chart in ${CHARTS} ; do \
		helm package --version ${ASTRONOMER_VERSION} -d ${OUTPUT} charts/$${chart} || exit 1; \
	done; \
	helm repo index docs --url ${URL}
